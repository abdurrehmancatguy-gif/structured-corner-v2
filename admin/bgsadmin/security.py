"""Who may talk to the admin, and which files a request may name.

The admin has no login yet and listens only on 127.0.0.1, so the threats are
web pages open in the owner's own browser: a page that rebinds a hostname to
127.0.0.1 (stopped by the Host check), a page that posts to localhost
(stopped by the Origin and Fetch Metadata checks, JSON-only bodies and the
per-run token), and script on the storefront preview, which shares this
origin (stopped by serving the admin page only to top-level navigations,
COOP, and a storefront CSP that forbids network calls, the shopper sign-in
provider's token endpoint alone excepted). See
docs/PLAN.md, security_model.
"""
import hmac
import json
import os
import pathlib
import re
import stat

from .errors import ApiError
from .schema.settings import AUTH_DOMAIN

ADMIN_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
             "media-src 'self' blob:; connect-src 'self'; frame-src 'self'; font-src 'self'; "
             "form-action 'none'; base-uri 'none'; frame-ancestors 'none'")

ADMIN_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": ADMIN_CSP,
}

# The storefront preview keeps flow/server.py's no-store headers, so a rebuild
# shows on reload. Its connect-src lets a store page's script reach one place
# only: the shopper sign-in provider in settings.json "auth", whose token
# endpoint the account page posts a sign-in's code to. The admin API, on this
# same origin, stays out of reach, so a script on a store page could not drive
# the API even if it somehow held the token. Without sign-in set up it is
# connect-src 'none', as before.
STOREFRONT_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "connect-src 'none'",
}

# The domains build.py accepts: a host name, reached over https, or
# 127.0.0.1 with a port, over plain http, which only the admin's tests use.
SIGNIN_TEST_DOMAIN = re.compile(r"127\.0\.0\.1:[1-9][0-9]{0,4}")
_SIGNIN = {}


def signin_origin(cfg):
    """The sign-in provider's origin from settings.json, or None. Read again
    whenever the file changes, so a save in Settings counts from the next
    page load."""
    path = cfg.content_file("settings")
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if _SIGNIN.get("key") != key:
        try:
            auth = json.loads(path.read_text(encoding="utf-8")).get("auth")
            dom = auth.get("domain") if isinstance(auth, dict) else None
        except (OSError, ValueError, AttributeError):
            dom = None
        origin = None
        if isinstance(dom, str) and re.fullmatch(AUTH_DOMAIN, dom):
            origin = "https://" + dom
        elif isinstance(dom, str) and SIGNIN_TEST_DOMAIN.fullmatch(dom):
            origin = "http://" + dom
        _SIGNIN.clear()
        _SIGNIN.update(key=key, origin=origin)
    return _SIGNIN.get("origin")


def storefront_headers(cfg):
    origin = signin_origin(cfg)
    if not origin:
        return STOREFRONT_HEADERS
    return dict(STOREFRONT_HEADERS, **{"Content-Security-Policy": "connect-src " + origin})

SAFE_METHODS = ("GET", "HEAD")


def check_host(handler, cfg):
    host = (handler.headers.get("Host") or "").strip().lower()
    if host not in cfg.hosts:
        raise ApiError(421, "bad_host", "Wrong host.")


def check_admin_page(handler):
    """The admin HTML carries the token, so only a real top-level visit gets
    it: not fetch(), not an iframe, not a navigation started by another site."""
    h = handler.headers
    mode, dest, site = h.get("Sec-Fetch-Mode"), h.get("Sec-Fetch-Dest"), h.get("Sec-Fetch-Site")
    if mode is not None and mode != "navigate":
        raise ApiError(403, "not_navigation", "Open the admin by typing its address.")
    if dest is not None and dest != "document":
        raise ApiError(403, "not_navigation", "The admin cannot be shown inside another page.")
    if site is not None and site not in ("none", "same-origin"):
        raise ApiError(403, "not_navigation", "Open the admin by typing its address, not from a link on another site.")


def check_api(handler, cfg, token, method):
    """Every API call carries the token; every change also carries our Origin."""
    sent = handler.headers.get("X-Admin-Token") or ""
    if not token or not hmac.compare_digest(sent.encode(), token.encode()):
        raise ApiError(401, "bad_token", "The admin restarted or this page is stale: reload it.")
    site = handler.headers.get("Sec-Fetch-Site")
    if site is not None and site != "same-origin":
        raise ApiError(403, "forbidden_origin", "Requests must come from the admin itself.")
    if method not in SAFE_METHODS:
        origin = handler.headers.get("Origin")
        if not origin or origin == "null" or origin not in cfg.origins:
            raise ApiError(403, "forbidden_origin", "Requests must come from the admin itself.")


def safe_join(root, rel, must_exist=True):
    """Resolve rel under root, or return None.

    Refused: empty, absolute, backslashes, NUL, '.' or '..' segments, any
    segment starting with a dot (no .backups, no .git), a symlink on any
    component, and anything that resolves outside root."""
    if not isinstance(rel, str) or not rel or "\x00" in rel or "\\" in rel or rel.startswith("/"):
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return None
    root = pathlib.Path(root).resolve()
    cur = root
    for i, p in enumerate(parts):
        cur = cur / p
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            if must_exist or i != len(parts) - 1:
                return None
            break
        if stat.S_ISLNK(st.st_mode):
            return None
    real = os.path.realpath(cur)
    if not real.startswith(str(root) + os.sep):
        return None
    return cur
