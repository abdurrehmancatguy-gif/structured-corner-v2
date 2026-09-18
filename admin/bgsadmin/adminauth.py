"""Who may open the admin.

Shoppers sign in to the shop with the Auth0 application in
flow/content/settings.json. The admin has a second, separate application of
its own, and a list of the people allowed in. A shopper account, however
valid, is not an admin account: the two applications share nothing but the
tenant, and the admin refuses any address that is not on its list.

The settings live outside flow/ (which is published) and outside git:
admin/local/admin-auth.json, or the environment, which is how a host sets
them:

    {"domain": "dev-xxxx.us.auth0.com",
     "client_id": "the admin application's Client ID",
     "base_url": "https://admin.example.com",
     "allowed": ["owner@example.com"]}

    BGS_ADMIN_AUTH_DOMAIN, BGS_ADMIN_AUTH_CLIENT_ID, BGS_ADMIN_BASE_URL,
    BGS_ADMIN_ALLOWED (addresses separated by commas)

No client secret is kept: the admin is a public client and signs in with the
Authorization Code flow and PKCE, as the storefront does. The code is
exchanged from the server, over TLS, and who signed in is read from the
provider's own /userinfo with that token, so nothing the browser sends
decides who anyone is.

The signed-in browser holds one cookie: the address, the name and the moment
it stops counting, signed with a key in admin/local/session-key (made on
demand, kept at 0600). Nothing in it is trusted without that signature. It is
HttpOnly and SameSite=Lax, and Secure whenever the admin is served over
https. It does not replace the per-run token or the Origin checks in
security.py: an API call still carries both.

On this machine (127.0.0.1) the admin opens as it always has, with no login,
which is what the owner asked for. It is required the moment the admin
listens on anything else, and BGS_ADMIN_REQUIRE_LOGIN=1 asks for it here too.
"""
import base64
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import ssl
import stat
import time
import urllib.error
import urllib.parse
import urllib.request

from .errors import ApiError
from .store.base import CannotStart
from .schema.settings import AUTH_CLIENT_ID, AUTH_DOMAIN

# the same shapes the shop's own sign-in settings are checked against, and a
# provider on 127.0.0.1 with a port, which is how the tests stand one in
DOMAIN = re.compile(AUTH_DOMAIN)
CLIENT_ID = re.compile(AUTH_CLIENT_ID)
TEST_DOMAIN = re.compile(r"127\.0\.0\.1:[1-9][0-9]{0,4}")

COOKIE = "bgsadmin"
FLOW_COOKIE = "bgsadmin_signin"
SESSION_SECONDS = 12 * 60 * 60
FLOW_SECONDS = 10 * 60
SCOPE = "openid profile email"
TIMEOUT = 15


class NotConfigured(CannotStart):
    """The admin needs a login here and its settings are missing or wrong."""


def _b64(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text):
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _emails(value):
    """The allowed addresses, lower case, from a list or a comma-separated line."""
    if isinstance(value, str):
        value = value.split(",")
    out = []
    for item in value or []:
        if not isinstance(item, str):
            raise NotConfigured("Every allowed address must be text.")
        item = item.strip().lower()
        if item:
            if "@" not in item or item.startswith("@") or item.endswith("@") or " " in item:
                raise NotConfigured("%s is not an email address." % item)
            out.append(item)
    return out


class Settings:
    """The admin application and its list of people, from the environment
    first (a host sets those) and then admin/local/admin-auth.json."""

    def __init__(self, domain, client_id, base_url, allowed):
        self.domain = domain
        self.client_id = client_id
        self.base_url = base_url.rstrip("/")
        self.allowed = allowed
        self.http = bool(TEST_DOMAIN.fullmatch(domain))   # a test provider on 127.0.0.1

    @property
    def issuer(self):
        return ("http://" if self.http else "https://") + self.domain

    def url(self, path, **params):
        return self.issuer + path + ("?" + urllib.parse.urlencode(params) if params else "")

    @property
    def redirect_uri(self):
        return self.base_url + "/admin/callback"

    def allows(self, email):
        return isinstance(email, str) and email.strip().lower() in self.allowed


def path_of(repo):
    return pathlib.Path(repo) / "admin" / "local" / "admin-auth.json"


def settings(repo):
    """The admin's login settings, or None when nothing is set up."""
    env = os.environ
    raw = {"domain": env.get("BGS_ADMIN_AUTH_DOMAIN"), "client_id": env.get("BGS_ADMIN_AUTH_CLIENT_ID"),
           "base_url": env.get("BGS_ADMIN_BASE_URL"), "allowed": env.get("BGS_ADMIN_ALLOWED")}
    path = path_of(repo)
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise NotConfigured("%s cannot be read: %s" % (path, e))
        if not isinstance(doc, dict):
            raise NotConfigured("%s must hold an object." % path)
        for k in raw:
            if raw[k] is None:
                raw[k] = doc.get(k)
    if not any(raw.values()):
        return None
    missing = [k for k in ("domain", "client_id", "base_url") if not raw.get(k)]
    if missing:
        raise NotConfigured("The admin's login needs %s (%s or the environment)."
                            % (" and ".join(missing), path_of(repo)))
    domain, client_id, base_url = raw["domain"].strip(), raw["client_id"].strip(), raw["base_url"].strip()
    if not (DOMAIN.fullmatch(domain) or TEST_DOMAIN.fullmatch(domain)):
        raise NotConfigured("The admin's login domain must be a host name like dev-abc123.us.auth0.com.")
    if not CLIENT_ID.fullmatch(client_id):
        raise NotConfigured("The admin's login client_id must be the application's Client ID.")
    parts = urllib.parse.urlsplit(base_url)
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment:
        raise NotConfigured("The admin's base_url must be the address the admin is served at, like https://admin.example.com.")
    if parts.scheme == "http" and parts.hostname not in ("127.0.0.1", "localhost"):
        raise NotConfigured("The admin's base_url must be https anywhere but this machine.")
    allowed = _emails(raw.get("allowed"))
    if not allowed:
        raise NotConfigured("The admin's login needs at least one allowed address (\"allowed\" in %s)."
                            % path_of(repo))
    if parts.path.strip("/"):
        raise NotConfigured("The admin's base_url is the address it is served at, with no path after it.")
    return Settings(domain, client_id, parts.scheme + "://" + parts.netloc.lower(), allowed)


LOCAL = ("127.0.0.1", "localhost", "::1")


def required(cfg):
    """A login is asked for off this machine: when the admin binds anything
    but the loopback, when its own address is a public one (a proxy in front
    of it still serves it to the world), and wherever it is set to be."""
    if str(os.environ.get("BGS_ADMIN_REQUIRE_LOGIN") or "").strip().lower() not in ("", "0", "false", "no", "off"):
        return True
    if cfg.host not in LOCAL:
        return True
    base = getattr(cfg, "base_url", None)
    if base:
        host = (urllib.parse.urlsplit(base).hostname or "").lower()
        if host and host not in LOCAL:
            return True
    return False


# ---- the signed cookies ---------------------------------------------------------------

def key(repo):
    """The key that signs this admin's cookies, made once, readable only by
    its owner. A new key signs everyone out, which is what losing it means."""
    path = pathlib.Path(repo) / "admin" / "local" / "session-key"
    try:
        raw = path.read_bytes().strip()
        if len(raw) >= 32:
            # O_CREAT sets a mode only for a file it makes, so one that was
            # already there is put back to its owner alone before it is used
            if stat.S_IMODE(path.stat().st_mode) != stat.S_IRUSR | stat.S_IWUSR:
                os.chmod(str(path), stat.S_IRUSR | stat.S_IWUSR)
            return raw
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = base64.b64encode(secrets.token_bytes(48))
    tmp = path.with_name(".%s.%s.tmp" % (path.name, os.getpid()))
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, stat.S_IRUSR | stat.S_IWUSR)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    os.replace(str(tmp), str(path))
    return raw


def seal(secret, payload, seconds):
    """A value the browser keeps and cannot change: the fields, when they stop
    counting, and a signature over both."""
    body = dict(payload, exp=int(time.time()) + seconds)
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return raw + "." + _b64(hmac.new(secret, raw.encode("ascii"), hashlib.sha256).digest())


def unseal(secret, value):
    """What seal() put in, or None: a wrong signature, a changed field, an
    unreadable value and an expired one all answer the same way."""
    if not value or "." not in value:
        return None
    raw, sig = value.rsplit(".", 1)
    try:
        want = _b64(hmac.new(secret, raw.encode("ascii"), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, want):
            return None
        body = json.loads(_unb64(raw))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    if not isinstance(body, dict) or not isinstance(body.get("exp"), int) or body["exp"] < time.time():
        return None
    return body


def cookies(handler):
    """Every value the browser sent for each cookie name, in order. A name can
    arrive more than once (another path, another domain, or planted by a page
    on a neighbouring site), so nothing here picks a winner: the callers try
    each value and take the one that is signed."""
    out = {}
    for header in handler.headers.get_all("Cookie") or []:
        for part in header.split(";"):
            name, _, value = part.strip().partition("=")
            if name:
                out.setdefault(name, []).append(value)
    return out


def sealed(handler, secret, name):
    """The first value of this cookie that carries our signature, or None."""
    for value in cookies(handler).get(name, []):
        body = unseal(secret, value)
        if body is not None:
            return body
    return None


def cookie_header(name, value, seconds, https, path="/admin"):
    bits = ["%s=%s" % (name, value), "Path=%s" % path, "HttpOnly", "SameSite=Lax"]
    bits.append("Max-Age=%d" % seconds)
    if not seconds:
        bits.append("Expires=Thu, 01 Jan 1970 00:00:00 GMT")
    if https:
        bits.append("Secure")
    return "; ".join(bits)


def who(cfg, handler):
    """The person this request is signed in as, or None."""
    body = sealed(handler, key(cfg.repo), COOKIE)
    if not body or not isinstance(body.get("email"), str):
        return None
    return body


# ---- the exchange with the provider ---------------------------------------------------

def _post(url, form, http_ok):
    data = urllib.parse.urlencode(form).encode("ascii")
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Content-Type": "application/x-www-form-urlencoded",
                                          "Accept": "application/json"})
    return _send(req, http_ok)


def _get(url, token, http_ok):
    req = urllib.request.Request(url, method="GET",
                                 headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
    return _send(req, http_ok)


def _send(req, http_ok):
    if req.full_url.startswith("http://") and not http_ok:
        raise ApiError(502, "signin_failed", "The sign-in provider must be reached over https.")
    ctx = None if req.full_url.startswith("http://") else ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            return json.loads(r.read(1 << 20).decode("utf-8"))
    except (urllib.error.URLError, ValueError, OSError):
        raise ApiError(502, "signin_failed", "The sign-in provider did not answer as expected.")


def start(cfg, conf):
    """Where to send the browser to sign in, and the cookie that remembers
    this attempt: the state the provider must send back, and the PKCE
    verifier only this server knows."""
    verifier = _b64(secrets.token_bytes(48))
    state = _b64(secrets.token_bytes(24))
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    url = conf.url("/authorize", response_type="code", client_id=conf.client_id,
                   redirect_uri=conf.redirect_uri, scope=SCOPE, state=state,
                   nonce=_b64(secrets.token_bytes(16)), code_challenge=challenge,
                   code_challenge_method="S256")
    cookie = seal(key(cfg.repo), {"state": state, "verifier": verifier}, FLOW_SECONDS)
    return url, cookie


def finish(cfg, conf, handler, params):
    """The provider sent the browser back: check the state against the cookie,
    trade the code for a token and ask the provider whose it is. Returns the
    person, or raises ApiError with what to tell them."""
    attempt = sealed(handler, key(cfg.repo), FLOW_COOKIE)
    if not attempt:
        raise ApiError(400, "signin_expired", "That sign-in took too long or was started elsewhere. Try again.")
    if params.get("error"):
        raise ApiError(403, "signin_refused", "The sign-in was not completed.")
    state, code = params.get("state"), params.get("code")
    if not state or not hmac.compare_digest(str(state), str(attempt.get("state", ""))):
        raise ApiError(400, "signin_state", "That sign-in did not come back the way it went out. Try again.")
    if not code:
        raise ApiError(400, "signin_state", "The provider sent no code back.")
    token = _post(conf.url("/oauth/token"),
                  {"grant_type": "authorization_code", "client_id": conf.client_id, "code": code,
                   "code_verifier": attempt["verifier"], "redirect_uri": conf.redirect_uri}, conf.http)
    access = token.get("access_token")
    if not isinstance(access, str) or not access:
        raise ApiError(502, "signin_failed", "The sign-in provider did not answer as expected.")
    info = _get(conf.url("/userinfo"), access, conf.http)
    email = info.get("email") if isinstance(info, dict) else None
    if not isinstance(email, str) or not email.strip():
        raise ApiError(403, "signin_refused", "That account has no email address, so the admin cannot let it in.")
    if info.get("email_verified") is not True:
        raise ApiError(403, "signin_refused", "That email address is not verified yet, so the admin cannot let it in.")
    if not conf.allows(email):
        raise ApiError(403, "not_allowed", "This account is not on the admin's list.")
    name = info.get("name") if isinstance(info.get("name"), str) else email
    return {"email": email.strip().lower(), "name": name[:80]}
