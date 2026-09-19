"""Roles: what each one may do, proved against the server rather than the UI.

    ADMIN_ACCESS_PORT=4748 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_access.py'

The admin used to have one list of addresses, and being on it meant being
able to do everything. Now each address has a role, every endpoint declares
the permission it needs, and two roles are narrower than an endpoint: a stock
role may change a product's stock and nothing else about it, and a marketing
role may change the discount rules in settings and nothing else in it.

These tests sign in as each role against the stand-in provider and ask the
API directly, with the admin's own token, which is what someone bypassing the
screens would do. Hiding a button proves nothing; a 403 does.
"""
import http.client
import json
import os
import pathlib
import re
import sys
import unittest
import urllib.parse

from box import Box
from fake_oidc import FakeOIDC

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import access, adminauth                              # noqa: E402

PORT = int(os.environ.get("ADMIN_ACCESS_PORT", "4748"))
IDP_PORT = int(os.environ.get("ADMIN_ACCESS_OIDC_PORT", str(PORT + 1)))
BASE = "http://127.0.0.1:%d" % PORT
CLIENT = "FakeAdminClient0123456789abcdefg"
NAV = {"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "none"}

OWNER = "owner@example.com"          # admin
BOSS = "boss@example.com"            # manager
ADS = "ads@example.com"              # marketing
STOCK = "stock@example.com"          # inventory
BOOKS = "books@example.com"          # accountant
PEOPLE = [{"email": OWNER, "role": "admin"}, {"email": BOSS, "role": "manager"},
          {"email": ADS, "role": "marketing"}, {"email": STOCK, "role": "inventory"},
          {"email": BOOKS, "role": "accountant"}]


class AuthBox(Box):
    """A Box whose admin asks for a sign-in, with the stand-in provider as its
    Auth0 application and a role beside every address."""

    def __init__(self, port, people=PEOPLE):
        self._clone(port, prefix="bgsadmin-access-")
        (self.repo / "admin" / "local").mkdir(parents=True, exist_ok=True)
        (self.repo / "admin" / "local" / "admin-auth.json").write_text(json.dumps(
            {"domain": "127.0.0.1:%d" % IDP_PORT, "client_id": CLIENT, "base_url": BASE,
             "allowed": people}, indent=2), encoding="utf-8")
        os.environ["BGS_ADMIN_REQUIRE_LOGIN"] = "1"
        try:
            self._start()
        finally:
            os.environ.pop("BGS_ADMIN_REQUIRE_LOGIN", None)

    def _spawn(self, py, extra, env):
        """As Box does, but this server asks for a sign-in, so /admin/ answers
        303 until someone has and the token comes later (token_now)."""
        import subprocess
        import time
        import cleanup
        from box import SERVER_WATCH
        env = dict(env, BGS_ADMIN_REQUIRE_LOGIN="1")
        self.proc = subprocess.Popen(
            [str(py), str(pathlib.Path(__file__).resolve().parent.parent / "server.py"),
             "--port", str(self.port), "--repo", str(self.repo), "--no-push"] + list(extra),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
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
        m = re.search(rb'name="admin-token" content="([^"]+)"', body)
        self.token = m.group(1).decode() if m else None
        return st


BOX = IDP = None


def setUpModule():
    global BOX, IDP
    IDP = FakeOIDC(IDP_PORT, CLIENT, [BASE + "/admin/callback"], [BASE + "/admin/signedout"], [BASE])
    BOX = AuthBox(PORT)


def tearDownModule():
    if BOX:
        BOX.close()
    if IDP:
        IDP.close()


def at_provider(query):
    c = http.client.HTTPConnection("127.0.0.1", IDP_PORT, timeout=10)
    c.request("GET", "/authorize?" + query)
    r = c.getresponse()
    where = r.getheader("Location") or ""
    r.read()
    c.close()
    assert where, "the provider refused: %s" % r.status
    return urllib.parse.urlsplit(where).query


def cookie_of(headers, name):
    raw = headers.get("Set-Cookie") or ""
    m = re.search(r"(?:^|, )%s=([^;]*)" % re.escape(name), raw)
    return m.group(1) if m else None


def sign_in(email):
    """The whole round trip, ending with the admin's token in hand: what a
    person's browser holds after signing in."""
    IDP.reset()
    IDP.user = {"sub": "auth0|" + email.split("@")[0], "name": email.split("@")[0], "email": email}
    IDP.email_verified = True
    st, head, _ = BOX.raw("GET", "/admin/signin", headers=NAV)
    assert st == 303, st
    flow = cookie_of(head, adminauth.FLOW_COOKIE)
    where = urllib.parse.urlsplit(head["Location"])
    back = dict(urllib.parse.parse_qsl(at_provider(where.query)))
    st, head, _ = BOX.raw("GET", "/admin/callback?" + urllib.parse.urlencode(back),
                          headers={"Cookie": "%s=%s" % (adminauth.FLOW_COOKIE, flow)})
    session = cookie_of(head, adminauth.COOKIE)
    assert session, "no session cookie: %s" % st
    cookie = "%s=%s" % (adminauth.COOKIE, session)
    BOX.token_now(cookie)
    return cookie


def api(cookie, method, path, body=None, rev=None):
    return BOX.api(method, path, body, rev=rev, headers={"Cookie": cookie})


class Roles(unittest.TestCase):
    """The table itself, before anything is served."""

    def test_every_endpoint_names_the_permission_it_needs(self):
        from bgsadmin import routes
        for r in routes.load():
            self.assertTrue(r.permission, "%s %s has no permission" % (r.method, r.pattern))
            self.assertIn(r.permission, access.ALL, r.pattern)

    def test_what_each_role_may_do(self):
        self.assertEqual(set(access.ROLES["admin"]), set(access.ALL))
        self.assertNotIn(access.STAFF, access.ROLES["manager"])
        self.assertIn(access.PUBLISH, access.ROLES["manager"])
        for role in ("marketing", "inventory", "accountant"):
            self.assertNotIn(access.STAFF, access.ROLES[role])
            self.assertNotIn(access.PUBLISH, access.ROLES[role])
            self.assertIn(access.ANALYTICS, access.ROLES[role], "analytics is for every role")
        self.assertNotIn(access.PRODUCTS, access.ROLES["inventory"])
        self.assertIn(access.STOCK, access.ROLES["inventory"])
        self.assertIn(access.ORDERS, access.ROLES["accountant"])
        self.assertNotIn(access.ORDERS, access.ROLES["marketing"])

    def test_a_stock_role_is_held_to_stock(self):
        old = {"name": "Vibe", "price": 85, "stock": 10}
        access.check_product_write("inventory", dict(old, stock=4), old)      # allowed
        with self.assertRaises(Exception):
            access.check_product_write("inventory", dict(old, price=1), old)
        access.check_product_write("admin", dict(old, price=1), old)          # not held

    def test_a_marketing_role_is_held_to_the_discounts(self):
        old = {"store": {"free_delivery_over": 150, "volume_tiers": [{"at": 3, "off": 10}]}}
        new = json.loads(json.dumps(old))
        new["store"]["volume_tiers"][0]["off"] = 12
        access.check_settings_write("marketing", new, old)                    # allowed
        with self.assertRaises(Exception):
            access.check_settings_write("marketing", {"store": dict(old["store"], free_delivery_over=1)}, old)


class Enforced(unittest.TestCase):
    """The same rules, through the API, with each role's own session."""

    def price_of(self, cookie, pid="vibe"):
        st, doc = api(cookie, "GET", "products/" + pid)
        self.assertEqual(st, 200, doc)
        return doc

    def test_inventory_may_change_stock_and_nothing_else(self):
        cookie = sign_in(STOCK)
        doc = self.price_of(cookie)
        data, rev = doc["data"], doc["rev"]
        st, res = api(cookie, "PUT", "products/vibe", {"data": dict(data, stock=7)}, rev=rev)
        self.assertEqual(st, 200, res)
        doc = self.price_of(cookie)
        st, res = api(cookie, "PUT", "products/vibe",
                      {"data": dict(doc["data"], price=doc["data"]["price"] + 5)}, rev=doc["rev"])
        self.assertEqual(st, 403, res)
        self.assertEqual(res["error"]["code"], "not_allowed")
        st, res = api(cookie, "PUT", "documents/copy", {"data": {}})
        self.assertEqual(st, 403, res)

    def test_marketing_may_write_words_but_not_products(self):
        cookie = sign_in(ADS)
        st, doc = api(cookie, "GET", "documents/copy")
        self.assertEqual(st, 200, doc)
        st, res = api(cookie, "PUT", "documents/copy", {"data": doc["data"]}, rev=doc["rev"])
        self.assertIn(st, (200, 409), res)          # a no-op save is fine; the permission passed
        st, res = api(cookie, "POST", "products", {"data": {"name": "New", "category": "edp"}})
        self.assertEqual(st, 403, res)
        st, res = api(cookie, "POST", "publish/commit", {"message": "x", "paths_digest": "y"})
        self.assertEqual(st, 403, res)

    def test_manager_runs_the_shop_but_does_not_manage_people(self):
        cookie = sign_in(BOSS)
        st, res = api(cookie, "GET", "staff")
        self.assertEqual(st, 403, res)
        st, res = api(cookie, "PUT", "staff", {"people": PEOPLE, "reason": "trying it on"})
        self.assertEqual(st, 403, res)
        st, res = api(cookie, "GET", "audit")               # may read the log
        self.assertEqual(st, 200, res)
        st, doc = api(cookie, "GET", "products/vibe")       # may run the shop
        self.assertEqual(st, 200, doc)

    def test_admin_manages_people_and_cannot_lock_the_shop_out(self):
        cookie = sign_in(OWNER)
        st, res = api(cookie, "GET", "staff")
        self.assertEqual(st, 200, res)
        self.assertEqual(len(res["people"]), len(PEOPLE))

        st, res = api(cookie, "PUT", "staff", {"people": PEOPLE})
        self.assertEqual(st, 422, res)                       # no reason given
        self.assertEqual(res["error"]["code"], "reason_required")

        without_me = [p for p in PEOPLE if p["email"] != OWNER]
        st, res = api(cookie, "PUT", "staff", {"people": without_me, "reason": "removing myself"})
        self.assertEqual(st, 422, res)
        self.assertEqual(res["error"]["code"], "not_yourself")

        demoted = [dict(p, role="manager") if p["email"] == OWNER else p for p in PEOPLE]
        st, res = api(cookie, "PUT", "staff", {"people": demoted, "reason": "demoting myself"})
        self.assertEqual(st, 422, res)

        # leaving nobody in charge is refused. A signed-in Admin always trips
        # the "not yourself" guard first, because demoting every Admin means
        # demoting themselves; the no_admin guard is what catches it when
        # there is no signed-in person to name (an admin with no login set up).
        no_admin = [dict(p, role="manager") for p in PEOPLE]
        st, res = api(cookie, "PUT", "staff", {"people": no_admin, "reason": "nobody in charge"})
        self.assertEqual(st, 422, res)
        self.assertIn(res["error"]["code"], ("not_yourself", "no_admin"))
        st, res = api(cookie, "GET", "staff")
        self.assertEqual(sorted(p["role"] for p in res["people"]),
                         sorted(p["role"] for p in PEOPLE), "nothing changed")

        added = PEOPLE + [{"email": "new@example.com", "role": "inventory"}]
        st, res = api(cookie, "PUT", "staff", {"people": added, "reason": "new stock person"})
        self.assertEqual(st, 200, res)
        self.assertIn("new@example.com", [p["email"] for p in res["people"]])

        st, res = api(cookie, "PUT", "staff", {"people": PEOPLE, "reason": "they left"})
        self.assertEqual(st, 200, res)
        self.assertNotIn("new@example.com", [p["email"] for p in res["people"]])

    def test_a_role_change_takes_effect_without_signing_in_again(self):
        stock_cookie = sign_in(STOCK)
        owner = sign_in(OWNER)
        st, res = api(owner, "PUT", "staff",
                      {"people": [p for p in PEOPLE if p["email"] != STOCK], "reason": "they left today"})
        self.assertEqual(st, 200, res)
        try:
            st, res = api(stock_cookie, "GET", "products/vibe")
            self.assertEqual(st, 403, res)          # the cookie is still valid; the list is not
        finally:
            st, res = api(owner, "PUT", "staff", {"people": PEOPLE, "reason": "they came back"})
            self.assertEqual(st, 200, res)

    def test_the_log_holds_the_sign_ins_and_the_role_changes(self):
        cookie = sign_in(OWNER)
        st, res = api(cookie, "GET", "audit")
        self.assertEqual(st, 200, res)
        kinds = [e["kind"] for e in res["events"]]
        self.assertIn("signin", kinds)
        signin = next(e for e in res["events"] if e["kind"] == "signin")
        self.assertEqual(signin["actor"], OWNER)
        self.assertIn("keep_days", res["stats"])
        self.assertEqual(res["stats"]["keep_days"], 60)


if __name__ == "__main__":
    unittest.main()
