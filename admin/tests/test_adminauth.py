"""Who may open the admin: its own sign-in, apart from the shop's.

    ADMIN_ADMINAUTH_PORT=4746 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_adminauth.py'

On this machine the admin opens with no login, as it always has. These tests
also run one that asks for a login (BGS_ADMIN_REQUIRE_LOGIN=1, which is what
being served anywhere else does), against the stand-in provider in
fake_oidc.py: the sign-in itself, the list of people, what a refused sign-in
sees, and that a signed-in browser still needs the admin's own token.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import http.client
import urllib.parse

import pgcluster
from box import Box
from fake_oidc import FakeOIDC

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import adminauth                                      # noqa: E402

PORT = int(os.environ.get("ADMIN_ADMINAUTH_PORT", "4746"))
IDP_PORT = int(os.environ.get("ADMIN_ADMINAUTH_OIDC_PORT", str(PORT + 1)))
BASE = "http://127.0.0.1:%d" % PORT
CLIENT = "FakeAdminClient0123456789abcdefg"
OWNER = "owner@example.com"
STRANGER = "someone@example.com"
NAV = {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "none"}


class AuthBox(Box):
    """A Box whose admin asks for a sign-in, with the stand-in provider as its
    Auth0 application."""

    def __init__(self, port, allowed=(OWNER,)):
        self._clone(port, prefix="bgsadmin-auth-")
        (self.repo / "admin" / "local").mkdir(parents=True, exist_ok=True)
        (self.repo / "admin" / "local" / "admin-auth.json").write_text(json.dumps(
            {"domain": "127.0.0.1:%d" % IDP_PORT, "client_id": CLIENT, "base_url": BASE,
             "allowed": list(allowed)}, indent=2), encoding="utf-8")
        os.environ["BGS_ADMIN_REQUIRE_LOGIN"] = "1"
        try:
            self._start()
        finally:
            os.environ.pop("BGS_ADMIN_REQUIRE_LOGIN", None)

    def _spawn(self, py, extra, env):
        """As Box does, but the server asks for a sign-in and /admin/ answers
        303 until someone has, so the token comes later (token_now)."""
        env = dict(env, BGS_ADMIN_REQUIRE_LOGIN="1")
        self.proc = subprocess.Popen([str(py), str(pathlib.Path(__file__).resolve().parent.parent / "server.py"),
                                      "--port", str(self.port), "--repo", str(self.repo), "--no-push"] + list(extra),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        import cleanup
        from box import SERVER_WATCH
        self._watch = cleanup.watchdog("/bin/sh", "-c", SERVER_WATCH, "bgs-box", self.proc.pid, self.tmp)
        for _ in range(150):
            if self.proc.poll() is not None:
                out = self.proc.stdout.read(4000).decode("utf-8", "replace")
                raise RuntimeError("the admin server did not start: %s" % out)
            try:
                if self.raw("GET", "/")[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(0.1)
        self.token = None

    def token_now(self, cookie):
        st, _, body = self.raw("GET", "/admin/", headers=dict(NAV, Cookie=cookie))
        self.token = re.search(rb'name="admin-token" content="([^"]+)"', body).group(1).decode()
        return st


BOX = IDP = None


def setUpModule():
    global BOX, IDP
    IDP = FakeOIDC(IDP_PORT, CLIENT, [BASE + "/admin/callback"], [BASE + "/admin/signedout"], [BASE])
    IDP.user = {"sub": "auth0|admin-1", "name": "The Owner", "email": OWNER}
    BOX = AuthBox(PORT)


def tearDownModule():
    if BOX:
        BOX.close()
    if IDP:
        IDP.close()


def at_provider(query):
    """Sign in at the stand-in provider and give back the query it sends the
    browser home with. The redirect is read, never followed: the admin's
    callback has to be asked with the attempt cookie, as a browser does."""
    c = http.client.HTTPConnection("127.0.0.1", IDP_PORT, timeout=10)
    c.request("GET", "/authorize?" + query)
    r = c.getresponse()
    where = r.getheader("Location") or ""
    r.read()
    c.close()
    assert where, "the provider refused: %s" % r.status
    return urllib.parse.urlsplit(where).query


def cookie_of(headers, name):
    """The value a response set for one cookie, or "" when it cleared it."""
    raw = headers.get("Set-Cookie") or ""
    m = re.search(r"(?:^|, )%s=([^;]*)" % re.escape(name), raw)
    return m.group(1) if m else None


def sign_in(email=OWNER, verified=True, break_state=False, drop_flow=False):
    """The whole round trip: /admin/signin, the provider, /admin/callback.
    Returns (status, headers, body) of the callback and the session cookie."""
    IDP.reset()
    IDP.user = {"sub": "auth0|admin-1", "name": "The Owner", "email": email}
    IDP.email_verified = verified
    st, head, _ = BOX.raw("GET", "/admin/signin", headers=NAV)
    assert st == 303, st
    flow = cookie_of(head, adminauth.FLOW_COOKIE)
    where = urllib.parse.urlsplit(head["Location"])
    params = dict(urllib.parse.parse_qsl(where.query))
    back = dict(urllib.parse.parse_qsl(at_provider(where.query)))
    if break_state:
        back["state"] = "another-state"
    headers = {} if drop_flow else {"Cookie": "%s=%s" % (adminauth.FLOW_COOKIE, flow)}
    st, head, body = BOX.raw("GET", "/admin/callback?" + urllib.parse.urlencode(back), headers=headers)
    return st, head, body, cookie_of(head, adminauth.COOKIE), params


class LocalAdmin(unittest.TestCase):
    """On this machine nothing changes: the admin opens straight away."""

    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT + 2)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def test_the_admin_on_this_machine_needs_no_sign_in(self):
        st, _, body = self.b.raw("GET", "/admin/", headers=NAV)
        self.assertEqual(st, 200)
        self.assertIn(b"admin-token", body)
        self.assertEqual(self.b.api("GET", "products")[0], 200)
        # and it has no sign-in pages at all
        self.assertEqual(self.b.raw("GET", "/admin/signin", headers=NAV)[0], 404)


class SignedOut(unittest.TestCase):
    def test_the_admin_page_sends_a_stranger_to_sign_in(self):
        st, head, _ = BOX.raw("GET", "/admin/", headers=NAV)
        self.assertEqual(st, 303)
        self.assertEqual(head["Location"], "/admin/signin")

    def test_the_api_says_to_sign_in_and_changes_nothing(self):
        st, _, body = BOX.raw("GET", "/admin/api/v1/products", headers={"X-Admin-Token": "anything"})
        self.assertEqual(st, 401)
        self.assertEqual(json.loads(body)["error"]["code"], "signin_required")

    def test_signin_sends_the_browser_to_the_provider_with_pkce(self):
        st, head, _ = BOX.raw("GET", "/admin/signin", headers=NAV)
        self.assertEqual(st, 303)
        where = urllib.parse.urlsplit(head["Location"])
        self.assertEqual((where.scheme, where.netloc, where.path), ("http", "127.0.0.1:%d" % IDP_PORT, "/authorize"))
        p = dict(urllib.parse.parse_qsl(where.query))
        self.assertEqual(p["client_id"], CLIENT)
        self.assertEqual(p["redirect_uri"], BASE + "/admin/callback")
        self.assertEqual(p["response_type"], "code")
        self.assertEqual(p["code_challenge_method"], "S256")
        self.assertRegex(p["code_challenge"], r"^[A-Za-z0-9_-]{43}$")
        self.assertTrue(p["state"] and p["nonce"])
        self.assertIn("openid", p["scope"].split())
        cookie = head["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertIn("Path=/admin", cookie)
        self.assertNotIn("Secure", cookie)          # this test's admin is http on 127.0.0.1


class SigningIn(unittest.TestCase):
    def tearDown(self):
        IDP.reset()

    def test_an_allowed_address_gets_in_and_can_work(self):
        # the callback answers a page of ours, since the browser arrives from
        # the provider and /admin/ is served only to a navigation that started
        # here; that page carries it on
        st, head, body, session, sent = sign_in()
        self.assertEqual(st, 200)
        self.assertIn(b'url=/admin/', body)
        self.assertIn(b"Signed in", body)
        self.assertTrue(session)
        cookie = "%s=%s" % (adminauth.COOKIE, session)
        self.assertEqual(BOX.token_now(cookie), 200)
        st, _, body = BOX.raw("GET", "/admin/api/v1/products",
                              headers={"X-Admin-Token": BOX.token, "Cookie": cookie})
        self.assertEqual(st, 200)
        self.assertTrue(json.loads(body)["items"])
        # the provider was asked who it was, with the token it had just given
        self.assertIn("userinfo", [e["kind"] for e in IDP.events])
        # and the cookie holds only who they are, signed
        body = adminauth.unseal(adminauth.key(BOX.repo), session)
        self.assertEqual(body["email"], OWNER)
        self.assertEqual(body["name"], "The Owner")

    def test_an_address_that_is_not_on_the_list_is_refused(self):
        st, head, body, session, _ = sign_in(email=STRANGER)
        self.assertEqual(st, 403)
        self.assertIsNone(session)
        self.assertIn(b"not on the admin", body)
        self.assertNotIn(STRANGER.encode(), body)          # the page names nobody
        self.assertEqual(BOX.raw("GET", "/admin/", headers=NAV)[0], 303)

    def test_an_unverified_address_is_refused(self):
        st, _, body, session, _ = sign_in(verified=False)
        self.assertEqual(st, 403)
        self.assertIsNone(session)
        self.assertIn(b"not verified", body)

    def test_signing_out_cannot_be_done_from_another_site(self):
        """A link on any page would otherwise sign the owner out of the admin
        and of the provider."""
        st, head, _ = BOX.raw("GET", "/admin/signout", headers={"Sec-Fetch-Mode": "navigate",
                                                                "Sec-Fetch-Dest": "document",
                                                                "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 403)
        self.assertIsNone(cookie_of(head, adminauth.COOKIE))

    def test_a_state_that_does_not_match_is_refused(self):
        st, _, _, session, _ = sign_in(break_state=True)
        self.assertEqual(st, 400)
        self.assertIsNone(session)

    def test_a_callback_without_the_attempt_cookie_is_refused(self):
        st, _, _, session, _ = sign_in(drop_flow=True)
        self.assertEqual(st, 400)
        self.assertIsNone(session)

    def test_a_refused_sign_in_at_the_provider_is_refused_here(self):
        IDP.reset()
        IDP.deny = True
        st, head, _ = BOX.raw("GET", "/admin/signin", headers=NAV)
        flow = cookie_of(head, adminauth.FLOW_COOKIE)
        where = urllib.parse.urlsplit(head["Location"])
        back = at_provider(where.query)
        st, _, _ = BOX.raw("GET", "/admin/callback?" + back,
                           headers={"Cookie": "%s=%s" % (adminauth.FLOW_COOKIE, flow)})
        self.assertEqual(st, 403)

    def test_a_used_code_cannot_be_used_again(self):
        st, head, _ = BOX.raw("GET", "/admin/signin", headers=NAV)
        flow = cookie_of(head, adminauth.FLOW_COOKIE)
        where = urllib.parse.urlsplit(head["Location"])
        back = at_provider(where.query)
        cookie = {"Cookie": "%s=%s" % (adminauth.FLOW_COOKIE, flow)}
        self.assertEqual(BOX.raw("GET", "/admin/callback?" + back, headers=cookie)[0], 200)
        self.assertEqual(BOX.raw("GET", "/admin/callback?" + back, headers=cookie)[0], 502)


class TheCookie(unittest.TestCase):
    def setUp(self):
        self.session = sign_in()[3]
        self.cookie = "%s=%s" % (adminauth.COOKIE, self.session)
        BOX.token_now(self.cookie)

    def test_a_changed_cookie_is_nobody(self):
        raw, sig = self.session.rsplit(".", 1)
        for bad in (raw + "." + ("a" if sig[0] != "a" else "b") + sig[1:], raw, "", "not.a.cookie",
                    raw.replace(raw[5], "x", 1) + "." + sig):
            st, head, _ = BOX.raw("GET", "/admin/", headers=dict(NAV, Cookie="%s=%s" % (adminauth.COOKIE, bad)))
            self.assertEqual(st, 303, bad[:20])
            self.assertEqual(head["Location"], "/admin/signin")

    def test_a_cookie_that_has_run_out_is_nobody(self):
        stale = adminauth.seal(adminauth.key(BOX.repo), {"email": OWNER, "name": "The Owner"}, -1)
        st, _, _ = BOX.raw("GET", "/admin/", headers=dict(NAV, Cookie="%s=%s" % (adminauth.COOKIE, stale)))
        self.assertEqual(st, 303)

    def test_a_cookie_signed_with_another_key_is_nobody(self):
        other = adminauth.seal(b"another key entirely, 32 bytes long", {"email": OWNER}, 600)
        st, _, _ = BOX.raw("GET", "/admin/", headers=dict(NAV, Cookie="%s=%s" % (adminauth.COOKIE, other)))
        self.assertEqual(st, 303)

    def test_being_signed_in_is_not_enough_for_the_api(self):
        st, _, body = BOX.raw("GET", "/admin/api/v1/products", headers={"Cookie": self.cookie})
        self.assertEqual(st, 401)
        self.assertEqual(json.loads(body)["error"]["code"], "bad_token")
        st, _, _ = BOX.raw("POST", "/admin/api/v1/build",
                           headers={"Cookie": self.cookie, "X-Admin-Token": BOX.token,
                                    "Origin": "https://somewhere.else", "Content-Type": "application/json"})
        self.assertEqual(st, 403)

    def test_signing_out_drops_the_cookie_and_ends_it_at_the_provider(self):
        st, head, _ = BOX.raw("GET", "/admin/signout", headers=dict(NAV, Cookie=self.cookie))
        self.assertEqual(st, 303)
        self.assertEqual(cookie_of(head, adminauth.COOKIE), "")
        where = urllib.parse.urlsplit(head["Location"])
        p = dict(urllib.parse.parse_qsl(where.query))
        self.assertEqual((where.path, p["client_id"], p["returnTo"]), ("/v2/logout", CLIENT, BASE + "/admin/signedout"))
        # and where the provider sends the browser back to says so and carries on
        st, head, body = BOX.raw("GET", "/admin/signedout")
        self.assertEqual(st, 200)
        self.assertIn(b"Signed out", body)
        self.assertEqual(cookie_of(head, adminauth.COOKIE), "")

    def test_the_same_cookie_sent_twice_cannot_push_the_real_one_aside(self):
        planted = "%s=%s; %s=%s" % (adminauth.COOKIE, self.session, adminauth.COOKIE, "planted.value")
        self.assertEqual(BOX.raw("GET", "/admin/", headers=dict(NAV, Cookie=planted))[0], 200)
        planted = "%s=%s; %s=%s" % (adminauth.COOKIE, "planted.value", adminauth.COOKIE, self.session)
        self.assertEqual(BOX.raw("GET", "/admin/", headers=dict(NAV, Cookie=planted))[0], 200)


class Settings(unittest.TestCase):
    """What the admin refuses to start with."""

    def run_server(self, repo, **env):
        """The admin, started once on a checkout of its own, with whatever
        settings this test gives it. It either refuses and says why, or it is
        stopped at once."""
        e = dict(pgcluster.clean_env(), BGS_ADMIN_REQUIRE_LOGIN="1", **env)
        p = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "server.py"),
                            "--port", str(PORT + 4), "--repo", str(repo), "--no-push"],
                           env=e, capture_output=True, text=True, timeout=60)
        return p

    def test_a_login_is_asked_for_off_this_machine(self):
        class Cfg:
            host = "0.0.0.0"
        self.assertTrue(adminauth.required(Cfg))
        Cfg.host = "127.0.0.1"
        self.assertFalse(adminauth.required(Cfg))
        os.environ["BGS_ADMIN_REQUIRE_LOGIN"] = "1"
        try:
            self.assertTrue(adminauth.required(Cfg))
        finally:
            os.environ.pop("BGS_ADMIN_REQUIRE_LOGIN", None)

    def test_settings_that_are_not_good_enough_are_refused(self):
        folder = BOX.repo
        path = adminauth.path_of(folder)
        before = path.read_text(encoding="utf-8")
        try:
            for doc, says in (
                    ({"domain": "127.0.0.1:%d" % IDP_PORT, "client_id": CLIENT, "base_url": BASE, "allowed": []},
                     "at least one allowed address"),
                    ({"domain": "127.0.0.1:%d" % IDP_PORT, "client_id": CLIENT, "allowed": [OWNER]},
                     "base_url"),
                    ({"domain": "not a domain", "client_id": CLIENT, "base_url": BASE, "allowed": [OWNER]},
                     "domain must be a host name"),
                    ({"domain": "dev-abc123.us.auth0.com", "client_id": "short", "base_url": BASE, "allowed": [OWNER]},
                     "client_id"),
                    ({"domain": "dev-abc123.us.auth0.com", "client_id": CLIENT, "base_url": "http://admin.example.com",
                      "allowed": [OWNER]}, "must be https"),
                    ({"domain": "dev-abc123.us.auth0.com", "client_id": CLIENT, "base_url": BASE,
                      "allowed": ["not-an-address"]}, "not an email address"),
                    ({"domain": "dev-abc123.us.auth0.com", "client_id": CLIENT,
                      "base_url": "https://example.com/admin", "allowed": [OWNER]}, "with no path after it")):
                path.write_text(json.dumps(doc), encoding="utf-8")
                with self.assertRaises(adminauth.NotConfigured) as cm:
                    adminauth.settings(folder)
                self.assertIn(says, cm.exception.message)
        finally:
            path.write_text(before, encoding="utf-8")

    def test_the_admin_will_not_start_off_this_machine_without_a_login(self):
        """A checkout with no login settings: the admin refuses to run rather
        than serve itself to anyone who can reach it."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgsadmin-nologin-"))
        self.addCleanup(shutil.rmtree, str(tmp), True)
        repo = tmp / "repo"
        subprocess.run(["git", "clone", "-q", str(pathlib.Path(__file__).resolve().parents[2]), str(repo)], check=True)
        p = self.run_server(repo)
        self.assertNotEqual(p.returncode, 0)
        self.assertIn("needs a login", p.stdout + p.stderr)

    def test_a_checkout_with_a_login_starts_and_asks_for_it(self):
        """The same checkout, with settings: it starts, and its admin page
        sends a stranger to sign in."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgsadmin-login-"))
        self.addCleanup(shutil.rmtree, str(tmp), True)
        repo = tmp / "repo"
        subprocess.run(["git", "clone", "-q", str(pathlib.Path(__file__).resolve().parents[2]), str(repo)], check=True)
        (repo / "admin" / "local").mkdir(parents=True, exist_ok=True)
        (repo / "admin" / "local" / "admin-auth.json").write_text(json.dumps(
            {"domain": "dev-abc123.us.auth0.com", "client_id": CLIENT,
             "base_url": "https://admin.example.com", "allowed": [OWNER]}), encoding="utf-8")
        proc = subprocess.Popen([sys.executable, str(pathlib.Path(__file__).resolve().parent.parent / "server.py"),
                                 "--port", str(PORT + 5), "--repo", str(repo), "--no-push"],
                                env=dict(pgcluster.clean_env(), BGS_ADMIN_REQUIRE_LOGIN="1"),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        self.addCleanup(proc.terminate)
        lines = []
        for _ in range(150):
            if proc.poll() is not None:
                break
            try:
                c = http.client.HTTPConnection("127.0.0.1", PORT + 5, timeout=10)
                c.request("GET", "/admin/", headers=dict(NAV, Host="localhost:%d" % (PORT + 5)))
                r = c.getresponse()
                where, status = r.getheader("Location"), r.status
                r.read()
                c.close()
                self.assertEqual((status, where), (303, "/admin/signin"))
                break
            except OSError:
                time.sleep(0.1)
        else:
            self.fail("the admin did not start: %s" % "".join(lines))


if __name__ == "__main__":
    unittest.main()
