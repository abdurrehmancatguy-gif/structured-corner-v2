"""Shopper sign-in on the storefront, against a stand-in for Auth0.

    ADMIN_SIGNIN_PORT=4792 ADMIN_SIGNIN_OIDC_PORT=4793 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_signin.py'

The storefront comes from a temporary clone (Box, --no-push). For the flow
itself its settings.json points sign-in at fake_oidc.FakeOIDC on 127.0.0.1,
the one host the shop reaches over plain http, on ADMIN_SIGNIN_OIDC_PORT (the
admin's port plus one unless set), and build.py rebuilds it. Headless Chrome
runs as a 390x844 phone and at 1440x900, with every host but localhost and
127.0.0.1 unresolvable, so nothing reaches the network.

The GitHub Pages, Netlify and bgscorner.com addresses are served by Chrome
itself (Fetch interception) from the same built files, Netlify's with its
pretty URLs, so the pages run at their real addresses with the real tenant's
settings; the tenant's /authorize, /oauth/token and /v2/logout are answered
there too, before anything leaves the browser. That checks the redirect_uri,
the web origin and the returnTo each site builds against the lists set in
Auth0, without calling Auth0.
"""
import base64
import hashlib
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
import urllib.parse

from box import Box
import cdp_pipe
from fake_oidc import FakeOIDC

PORT = int(os.environ.get("ADMIN_SIGNIN_PORT", "4792"))
IDP_PORT = int(os.environ.get("ADMIN_SIGNIN_OIDC_PORT", str(PORT + 1)))
SITE = "http://localhost:%d" % PORT
FAKE_CLIENT = "FakeShopClient0123456789abcdefgh"
J = json.dumps
# Every host but these two fails to resolve in the tests' Chrome.
OFFLINE = ["--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1"]

# The real tenant and the "bgs-corner" application's lists in Auth0.
TENANT = "dev-i8cqekmfe57ladb2.us.auth0.com"
CLIENT = "zqJhUwHScEpek3M2EAdOazOLYgy0Z9jC"
CALLBACKS = ["https://bgscorner.com/account.html", "https://bgscorner.com/account",
             "https://www.bgscorner.com/account.html", "https://www.bgscorner.com/account",
             "https://abdurrehmancatguy-gif.github.io/structured-corner-v2/account.html",
             "https://enchanting-daffodil-aca9b0.netlify.app/account.html",
             "https://enchanting-daffodil-aca9b0.netlify.app/account", "http://localhost:4310/account.html"]
LOGOUTS = ["https://bgscorner.com/", "https://www.bgscorner.com/",
           "https://abdurrehmancatguy-gif.github.io/structured-corner-v2/",
           "https://enchanting-daffodil-aca9b0.netlify.app/", "http://localhost:4310/"]
WEB_ORIGINS = ["https://bgscorner.com", "https://www.bgscorner.com", "https://abdurrehmancatguy-gif.github.io",
               "https://enchanting-daffodil-aca9b0.netlify.app", "http://localhost:4310"]

BOX = IDP = None


def setUpModule():
    global BOX, IDP
    BOX = Box(PORT)
    IDP = FakeOIDC(IDP_PORT, FAKE_CLIENT, [SITE + "/account.html"], [SITE + "/"], [SITE])


def tearDownModule():
    if IDP:
        IDP.close()
    if BOX:
        BOX.close()


def configure(domain, client_id):
    """Point the clone's sign-in somewhere and rebuild it, as a hand edit
    would: the admin refuses the fake provider's 127.0.0.1 domain."""
    s = BOX.repo / "flow" / "content" / "settings.json"
    d = json.loads(s.read_text(encoding="utf-8"))
    d["auth"] = {"domain": domain, "client_id": client_id}
    s.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    p = subprocess.run([sys.executable, "build.py"], cwd=str(BOX.repo / "flow"), capture_output=True, text=True, timeout=100)
    if p.returncode:
        raise RuntimeError("build failed: " + p.stderr)


def global_in(name):
    js = (BOX.repo / "flow" / "assets" / "catalogue.js").read_text(encoding="utf-8")
    return json.loads(re.search(r"^window\.%s = (.*);$" % name, js, re.M).group(1))


def words():
    return json.loads((BOX.repo / "flow" / "content" / "pages.json").read_text(encoding="utf-8"))


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def until(c, expr, timeout=20, what=None):
    """c.wait, riding out a navigation that swaps the page mid-question."""
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            if c.js(expr):
                return
        except (RuntimeError, TimeoutError):
            pass
        time.sleep(0.1)
    try:
        at = c.js("location.href")
    except (RuntimeError, TimeoutError):
        at = "?"
    raise AssertionError("timed out waiting for %s, at %s" % (what or expr, at))


def view(c, w, h, phone):
    c.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 3 if phone else 1,
                                                  "mobile": phone, "screenWidth": w, "screenHeight": h})
    c.call("Emulation.setTouchEmulationEnabled", {"enabled": phone, "maxTouchPoints": 5 if phone else 1})


def tap(c, sel, idx=0):
    """A click through Chrome's input pipeline, at the middle of the element."""
    c.js("document.querySelectorAll(%s)[%d].scrollIntoView({block: 'center'})" % (J(sel), idx))
    time.sleep(0.15)
    p = c.js("""(() => { const e = document.querySelectorAll(%s)[%d]; if (!e) return null;
      const r = e.getBoundingClientRect(), v = window.visualViewport, s = v ? v.scale : 1;
      return [(r.left + r.width / 2 - (v ? v.offsetLeft : 0)) * s, (r.top + r.height / 2 - (v ? v.offsetTop : 0)) * s]; })()"""
             % (J(sel), idx))
    if not p:
        raise AssertionError("nothing at %s" % sel)
    for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
        c.call("Input.dispatchMouseEvent", {"type": kind, "x": p[0], "y": p[1], "button": "left", "clickCount": 1})


READY = "document.readyState === 'complete' && 'BGS_AUTH' in window"
PANEL = """(() => { const p = document.querySelector('[data-signin]'); if (!p) return null;
  const box = (e) => { const r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return {text: e.textContent.trim(), h: r.height, fs: parseFloat(s.fontSize)}; };
  return {shown: !p.hidden && p.getBoundingClientRect().height > 0, heading: box(p.querySelector('h2')),
    body: box(p.querySelector('p')), buttons: [...p.querySelectorAll('[data-signin-go]')].map(box),
    msg: p.querySelector('[data-signinmsg]').textContent, busy: p.getAttribute('aria-busy'),
    views: [...document.querySelectorAll('[data-acctview]')].map((v) => v.hidden),
    capitals: [...p.querySelectorAll('*')].filter((e) => getComputedStyle(e).textTransform === 'uppercase').length,
    width: document.documentElement.scrollWidth, text: document.body.innerText}; })()"""
ME = """(() => { const m = document.querySelectorAll('[data-me="email"]'), a = document.querySelector('[data-meavatar]');
  return {name: document.querySelector('[data-me="name"]').textContent, email: m[0].textContent, row: m[1].textContent,
    picture: !!(a && a.querySelector('img')), panel: document.querySelector('[data-signin]').hidden,
    views: [...document.querySelectorAll('[data-acctview]')].map((v) => v.hidden)}; })()"""
LINKS = """(() => { const f = (a) => a && ({label: a.getAttribute('aria-label'), title: a.getAttribute('title'),
    signed: a.classList.contains('signed'), face: a.querySelector('.avatar') ? a.querySelector('.avatar').textContent : null,
    picture: !!a.querySelector('.avatar img'), svg: !!a.querySelector('svg') && getComputedStyle(a.querySelector('svg')).display !== 'none',
    h: a.getBoundingClientRect().height});
  return {head: f(document.querySelector('.mast a.act-acct')),
    tab: f([...document.querySelectorAll('.tabbar a')].find((a) => /(^|\\/)account(\\.html)?$/.test(a.getAttribute('href'))))}; })()"""
STORED = """(() => { const out = []; for (const s of [localStorage, sessionStorage])
  for (let i = 0; i < s.length; i++) out.push([s.key(i), s.getItem(s.key(i))]); return out; })()"""


class Browser(cdp_pipe.Chrome):
    """Headless Chrome that answers every https request itself: the pages of
    the sites in SITES from the clone's built files (Netlify's with its pretty
    URLs), and the real tenant's endpoints: /oauth/token with .token(request)
    -> (status, body), anything else there with a page that says it stopped.
    Every other request fails, so nothing is passed on to the network, which
    OFFLINE shuts out anyway. A paused request is answered the moment it is
    read, even while a command waits for its own answer: Chrome holds a
    command back while the navigation it would run in is paused."""
    SITES = {"https://abdurrehmancatguy-gif.github.io": ("/structured-corner-v2/", False),
             "https://enchanting-daffodil-aca9b0.netlify.app": ("/", True),
             "https://bgscorner.com": ("/", False), "https://www.bgscorner.com": ("/", False)}
    TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
             ".css": "text/css; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
             ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8"}
    QUIET = 1 << 30

    def __init__(self, w, h, phone, flow):
        super().__init__(w, h, args=OFFLINE)
        view(self, w, h, phone)
        self.flow = flow
        self.seen = []
        self.token = None
        self.k = self.QUIET
        self.call("Fetch.enable", {"patterns": [{"urlPattern": "https://*", "requestStage": "Request"}]})

    def send(self, method, params):
        """A command nobody waits for; call() drops its answer."""
        self.k += 1
        os.write(self.w, json.dumps({"id": self.k, "method": method, "params": params, "sessionId": self.sid}).encode() + b"\0")

    def call(self, method, params=None, browser=False, timeout=30):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}}
        if not browser and self.sid:
            msg["sessionId"] = self.sid
        os.write(self.w, json.dumps(msg).encode() + b"\0")
        while True:
            m = self._read(timeout)
            if m.get("method") == "Fetch.requestPaused":
                self.reply(m["params"])
            elif m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError("%s: %s" % (method, m["error"]))
                return m.get("result", {})
            elif m.get("id", 0) <= self.QUIET:
                self.events.append(m)

    def go(self, url):
        """Navigate without waiting for the page: until() waits for what matters."""
        self.send("Page.navigate", {"url": url})

    def fulfill(self, rid, status, ctype, body, more=None):
        h = [{"name": "Content-Type", "value": ctype}, {"name": "Cache-Control", "value": "no-store"}]
        h += [{"name": k, "value": v} for k, v in (more or {}).items()]
        self.send("Fetch.fulfillRequest", {"requestId": rid, "responseCode": status, "responseHeaders": h,
                                           "body": base64.b64encode(body).decode("ascii")})

    def reply(self, p):
        rid, req = p["requestId"], p["request"]
        u = urllib.parse.urlsplit(req["url"])
        if u.netloc == TENANT:
            self.seen.append({"method": req["method"], "url": req["url"], "body": req.get("postData"),
                              "headers": req.get("headers", {})})
            if u.path == "/oauth/token" and req["method"] == "POST" and self.token:
                status, body = self.token(req)
                cors = {"Access-Control-Allow-Origin": req.get("headers", {}).get("Origin", ""), "Vary": "Origin"}
                return self.fulfill(rid, status, "application/json", json.dumps(body).encode(), cors)
            return self.fulfill(rid, 200, "text/html; charset=utf-8", b"<!doctype html><title>Auth0</title><p>Stopped before Auth0.</p>")
        site = self.SITES.get("%s://%s" % (u.scheme, u.netloc))
        got = self.page(site, u.path) if site else None
        if got is None:
            return self.send("Fetch.failRequest", {"requestId": rid, "errorReason": "BlockedByClient"})
        self.fulfill(rid, 200, *got)

    def page(self, site, path):
        prefix, pretty = site
        if not path.startswith(prefix):
            return None
        rel = urllib.parse.unquote(path[len(prefix):]) or "index.html"
        if pretty and "/" not in rel and "." not in rel:
            rel += ".html"
        ext = os.path.splitext(rel)[1]
        ok = ("/" not in rel and ext in (".html", ".ico", ".txt")) or (
            rel.startswith("assets/") and ".." not in rel and rel != "assets/flow.css" and ext in self.TYPES)
        f = self.flow / rel
        if not ok or not f.is_file():
            return None
        body = f.read_bytes()
        if pretty and ext == ".html":
            # Netlify's pretty URLs: account.html is linked as /account and index.html as /
            body = re.sub(rb'href="([a-z0-9-]+)\.html', lambda m: b'href="/' + (b"" if m.group(1) == b"index" else m.group(1)), body)
        return self.TYPES[ext], body


@unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
class SigninFlow(unittest.TestCase):
    """The sign-in itself, against the fake provider on 127.0.0.1."""

    @classmethod
    def setUpClass(cls):
        configure("127.0.0.1:%d" % IDP_PORT, FAKE_CLIENT)
        w = words()
        cls.w = w["account"]["signin"]
        cls.signed_in = w["shell"]["header"]["signed_in"]

    def setUp(self):
        IDP.reset()
        self.c = None

    def tearDown(self):
        if self.c:
            self.c.close()

    # ---- helpers -----------------------------------------------------------------
    def open(self, w, h, phone, path="account.html"):
        if not self.c:
            self.c = cdp_pipe.Chrome(width=w, height=h, args=OFFLINE)
            view(self.c, w, h, phone)
        self.c.go(SITE + "/" + path)
        until(self.c, READY, 30)
        time.sleep(0.2)

    def fresh(self, w, h, phone, path="account.html"):
        if self.c:
            self.c.close()
            self.c = None
        self.open(w, h, phone, path)

    def js(self, expr):
        return self.c.js(expr)

    def label(self, name):
        return self.signed_in.replace("{name}", name)

    def signed_in_here(self):
        until(self.c, "location.search === '' && location.pathname.endsWith('/account.html') && "
                      "!!document.querySelector('[data-signin]') && document.querySelector('[data-signin]').hidden",
              20, what="the signed-in account page")

    def refused(self):
        until(self.c, "location.search === '' && !!document.querySelector('[data-signinmsg]') && "
                      "document.querySelector('[data-signinmsg]').textContent !== '' && "
                      "document.querySelector('[data-signin]').getAttribute('aria-busy') !== 'true'",
              20, what="a message on the sign-in panel")
        return self.js(PANEL)

    def profile(self):
        return self.js("localStorage.getItem('bgs_profile')")

    def no_errors(self):
        self.assertEqual(self.c.errors(), [], "the page threw or logged an error")

    def params(self, kind):
        return [e["params"] for e in IDP.events if e["kind"] == kind]

    # ---- signed out ----------------------------------------------------------------
    def test_a_shopper_who_is_not_signed_in_gets_the_panel_on_a_phone_and_a_desktop(self):
        for w, h, phone in ((390, 844, True), (1440, 900, False)):
            with self.subTest(width=w):
                self.fresh(w, h, phone)
                p = self.js(PANEL)
                self.assertTrue(p["shown"])
                self.assertEqual(p["views"], [True, True], "the account itself stays hidden")
                self.assertEqual((p["heading"]["text"], p["body"]["text"]), (self.w["heading"], self.w["body"]))
                self.assertEqual([b["text"] for b in p["buttons"]], [self.w["sign_in"], self.w["create"]])
                self.assertEqual((p["msg"], p["capitals"], p["width"]), ("", 0, w))
                for b in p["buttons"] + ([p["body"]] if phone else []):
                    self.assertGreaterEqual(b["fs"], 14)
                for b in p["buttons"]:
                    self.assertGreaterEqual(b["h"], 44)
                link = self.js(LINKS)["tab" if phone else "head"]
                self.assertEqual((link["signed"], link["face"], link["svg"]), (False, None, True))
                self.assertIsNone(self.profile())
                self.no_errors()
        # in Arabic the panel reads the dictionary's words
        ar = global_in("BGS_AR")
        self.js("document.querySelector('[data-langtoggle]').click()")
        p = self.js(PANEL)
        self.assertEqual((p["heading"]["text"], p["body"]["text"]), (ar[self.w["heading"]], ar[self.w["body"]]))
        self.assertEqual([b["text"] for b in p["buttons"]], [ar[self.w["sign_in"]], ar[self.w["create"]]])

    # ---- signing in ----------------------------------------------------------------
    def test_signing_in_on_a_desktop_shows_the_shopper_on_the_account_page_and_in_the_header(self):
        self.open(1440, 900, False)
        tap(self.c, '[data-signin-go=""]')
        self.signed_in_here()
        me = self.js(ME)
        self.assertEqual((me["name"], me["email"], me["row"], me["views"]),
                         ("Noor Haddad", "noor@example.com", "noor@example.com", [False, False]))
        until(self.c, "!!document.querySelector('[data-meavatar] img')", 5, what="the picture")
        head = self.js(LINKS)["head"]
        self.assertEqual((head["label"], head["signed"], head["svg"]), (self.label("Noor Haddad"), True, False))
        self.assertEqual(self.js("location.href"), SITE + "/account.html", "code and state leave the address bar")

        a = self.params("authorize")[0]
        self.assertEqual({k: a[k] for k in ("response_type", "client_id", "redirect_uri", "scope", "code_challenge_method")},
                         {"response_type": "code", "client_id": FAKE_CLIENT, "redirect_uri": SITE + "/account.html",
                          "scope": "openid profile email", "code_challenge_method": "S256"})
        self.assertNotIn("screen_hint", a)
        self.assertEqual((len(a["state"]), len(a["nonce"]), len(a["code_challenge"])), (22, 22, 43))
        tokens = [e for e in IDP.events if e["kind"] == "token"]
        self.assertEqual([(e["ok"], e["origin"], e["cookie"]) for e in tokens], [(True, SITE, False)])

        # the small profile is all that is kept: no token, and no attempt left over
        stored = self.js(STORED)
        self.assertNotIn("bgs_signin", [k for k, v in stored])
        for k, v in stored:
            self.assertNotIn("eyJ", v, k)
        prof = json.loads(self.profile())
        self.assertEqual(sorted(prof), ["email", "exp", "name", "picture", "sub"])
        self.assertEqual((prof["sub"], prof["picture"]), ("auth0|fake-shopper-1", IDP.base + "/picture.png"))
        self.assertGreater(prof["exp"], time.time() + 3600)

        # every other page knows who it is
        self.c.go(SITE + "/collection.html")
        until(self.c, READY + " && location.pathname.endsWith('/collection.html')", 20)
        self.assertEqual(self.js(LINKS)["head"]["label"], self.label("Noor Haddad"))
        self.no_errors()

    def test_creating_an_account_on_a_phone_goes_back_to_the_page_the_shopper_started_from(self):
        name = "L" + chr(0xE9) + "a Haddad"
        IDP.user = dict(IDP.user, name=name)
        try:
            start = SITE + "/product.html?p=royal-amber"
            self.open(390, 844, True, "product.html?p=royal-amber")
            height = self.js(LINKS)["tab"]["h"]
            tap(self.c, '.tabbar a[href="account.html"]')
            until(self.c, "location.pathname.endsWith('/account.html') && " + READY, 20)
            self.assertTrue(self.js(PANEL)["shown"])
            tap(self.c, '[data-signin-go="signup"]')
            until(self.c, "location.href === %s && %s" % (J(start), READY), 25, what="the product page again")
            until(self.c, "!!document.querySelector('.tabbar a.signed .avatar img')", 5, what="the picture on the tab")
            tab = self.js(LINKS)["tab"]
            self.assertEqual((tab["label"], tab["title"], tab["svg"]), (self.label(name), self.label(name), False))
            self.assertEqual(tab["h"], height, "the tab keeps its height")
            self.assertEqual(self.params("authorize")[0].get("screen_hint"), "signup")

            # the account page on a phone: the shopper, and a Sign out within reach
            tap(self.c, '.tabbar a[href="account.html"]')
            until(self.c, "location.pathname.endsWith('/account.html') && " + READY, 20)
            me = self.js(ME)
            self.assertEqual((me["name"], me["email"], me["panel"]), (name, "noor@example.com", True))
            out = self.js("""(() => { const b = document.querySelector('.acct-out'), r = b.getBoundingClientRect(),
              e = document.querySelector('[data-me="email"]');
              return {shown: getComputedStyle(b).display !== 'none', h: r.height, fs: parseFloat(getComputedStyle(b).fontSize),
                text: b.textContent, email: parseFloat(getComputedStyle(e).fontSize)}; })()""")
            self.assertEqual((out["shown"], out["text"]), (True, self.w["sign_out"]))
            self.assertGreaterEqual(out["h"], 44)
            self.assertGreaterEqual(min(out["fs"], out["email"]), 14)
            # and in Arabic the tab says who it is in Arabic
            ar = global_in("BGS_AR")
            self.js("document.querySelector('[data-langtoggle]').click()")
            self.assertEqual(self.js(LINKS)["tab"]["label"], ar[self.signed_in].replace("{name}", name))
            self.no_errors()
        finally:
            IDP.user = dict(IDP.user, name="Noor Haddad")

    # ---- refused -------------------------------------------------------------------
    def test_a_callback_with_a_state_that_was_not_sent_is_refused(self):
        IDP.wrong_state = True
        self.open(1440, 900, False)
        tap(self.c, '[data-signin-go=""]')
        p = self.refused()
        self.assertEqual((p["msg"], p["shown"], p["views"]), (self.w["failed"], True, [True, True]))
        self.assertNotIn("token", IDP.kinds(), "the code never went to the token endpoint")
        self.assertIsNone(self.profile())
        self.assertIsNone(self.js("sessionStorage.getItem('bgs_signin')"))
        self.assertFalse(self.js(LINKS)["head"]["signed"])
        # the next try starts afresh
        IDP.wrong_state = False
        tap(self.c, '[data-signin-go=""]')
        self.signed_in_here()
        self.no_errors()

    def test_an_id_token_with_another_nonce_is_refused(self):
        IDP.wrong_nonce = True
        self.open(390, 844, True)
        tap(self.c, '[data-signin-go=""]')
        p = self.refused()
        self.assertEqual((p["msg"], p["shown"], p["views"]), (self.w["failed"], True, [True, True]))
        self.assertEqual([e["ok"] for e in IDP.events if e["kind"] == "token"], [True], "the code was exchanged")
        self.assertIsNone(self.profile())
        self.assertFalse(self.js(LINKS)["tab"]["signed"])
        self.no_errors()

    def test_a_profile_past_its_expiry_reads_as_signed_out(self):
        self.open(390, 844, True, "index.html")
        now = int(time.time())
        prof = {"sub": "auth0|x", "name": "Noor Haddad", "email": "noor@example.com", "picture": "", "exp": now + 600}
        self.js("localStorage.setItem('bgs_profile', %s)" % J(J(prof)))
        self.open(390, 844, True)
        self.assertEqual(self.js(ME)["name"], "Noor Haddad")
        tab = self.js(LINKS)["tab"]
        self.assertEqual((tab["signed"], tab["face"]), (True, "N"), "no picture: the first letter")
        self.js("localStorage.setItem('bgs_profile', %s)" % J(J(dict(prof, exp=now - 5))))
        self.open(390, 844, True)
        p = self.js(PANEL)
        self.assertEqual((p["shown"], p["views"]), (True, [True, True]))
        self.assertFalse(self.js(LINKS)["tab"]["signed"])
        self.assertIsNone(self.profile(), "the expired profile is removed")
        self.no_errors()

    def test_a_refused_sign_in_reads_as_a_message_and_a_link_s_own_words_never_show(self):
        IDP.deny = True
        start = SITE + "/collection.html?cat=bakhoor"
        self.open(1440, 900, False, "collection.html?cat=bakhoor")
        tap(self.c, ".mast a.act-acct")
        until(self.c, "location.pathname.endsWith('/account.html') && " + READY, 20)
        tap(self.c, '[data-signin-go=""]')
        p = self.refused()
        self.assertEqual((p["msg"], p["shown"]), (self.w["cancelled"], True))
        self.assertNotIn("The shopper said no", p["text"])
        self.assertNotIn("token", IDP.kinds())
        self.assertIsNone(self.profile())
        # trying again still goes back to where the shopper started
        IDP.deny = False
        tap(self.c, '[data-signin-go=""]')
        until(self.c, "location.href === %s && %s && !!document.querySelector('.mast a.act-acct.signed')" % (J(start), READY),
              25, what="the collection again, signed in")
        self.js("localStorage.removeItem('bgs_profile')")
        # any other error, from a link anyone could write: the plain message, never its description
        self.c.go(SITE + "/account.html?error=server_error&error_description=" + urllib.parse.quote("Call 0500000000 to finish"))
        until(self.c, READY + " && location.search === ''", 20)
        p = self.js(PANEL)
        self.assertEqual(p["msg"], self.w["failed"])
        self.assertNotIn("0500000000", p["text"])
        self.no_errors()

    def test_a_callback_that_cannot_be_used_leaves_a_signed_in_shopper_on_their_account(self):
        self.open(1440, 900, False)
        tap(self.c, '[data-signin-go=""]')
        self.signed_in_here()
        a = [e for e in IDP.events if e["kind"] == "authorize"][-1]
        replay = "account.html?" + urllib.parse.urlencode({"code": a["code"], "state": a["params"]["state"]})

        def account_as_it_was(what, tokens):
            p, me = self.js(PANEL), self.js(ME)
            self.assertEqual((p["shown"], p["msg"], p["views"]), (False, "", [False, False]), what)
            self.assertNotEqual(p["busy"], "true", what)
            self.assertEqual((me["name"], me["email"]), ("Noor Haddad", "noor@example.com"), what)
            self.assertTrue(self.js(LINKS)["head"]["signed"], what)
            self.assertEqual(self.js("location.href"), SITE + "/account.html", what)
            self.assertEqual([e["ok"] for e in IDP.events if e["kind"] == "token"], tokens, what)
            self.assertIsNotNone(self.profile(), what)

        # the same callback again, and links anyone could write: nothing reaches the token endpoint
        for path in (replay, "account.html?code=made-up&state=made-up", "account.html?state=made-up",
                     "account.html?error=access_denied", "account.html?error=server_error&error_description=x"):
            IDP.reset()
            self.c.go(SITE + "/" + path)
            until(self.c, READY + " && location.search === ''", 20, what=path)
            time.sleep(0.3)
            account_as_it_was(path, [])
        # an attempt this tab kept, whose exchange the provider refuses
        IDP.reset()
        att = {"verifier": "v" * 43, "state": "kept-state", "nonce": "kept-nonce",
               "redirect_uri": SITE + "/account.html", "return_to": ""}
        self.js("sessionStorage.setItem('bgs_signin', %s)" % J(J(att)))
        self.c.go(SITE + "/account.html?code=unknown-code&state=kept-state")
        until(self.c, READY + " && location.search === '' && "
                      "document.querySelector('[data-signin]').getAttribute('aria-busy') === 'false'", 20,
              what="the exchange to end")
        account_as_it_was("a refused exchange", [False])
        # signed out, the same callback still reads as a message
        self.js("localStorage.removeItem('bgs_profile')")
        IDP.reset()
        self.c.go(SITE + "/" + replay)
        p = self.refused()
        self.assertEqual((p["msg"], p["shown"], p["views"]), (self.w["failed"], True, [True, True]))
        self.assertNotIn("token", IDP.kinds())
        self.no_errors()

    # ---- signing out ---------------------------------------------------------------
    def test_signing_out_forgets_the_shopper_and_goes_through_the_logout_endpoint(self):
        for w, h, phone, button in ((1440, 900, False, ".acctnav [data-signout]"), (390, 844, True, ".acct-out")):
            with self.subTest(width=w):
                IDP.reset()
                self.fresh(w, h, phone)
                tap(self.c, '[data-signin-go=""]')
                self.signed_in_here()
                tap(self.c, button)
                until(self.c, "location.href === %s && %s" % (J(SITE + "/"), READY), 20, what="the home page")
                self.assertEqual([(p["client_id"], p["returnTo"]) for p in self.params("logout")], [(FAKE_CLIENT, SITE + "/")])
                self.assertIsNone(self.profile())
                link = self.js(LINKS)["tab" if phone else "head"]
                self.assertEqual((link["signed"], link["svg"]), (False, True))
                self.no_errors()

    def test_a_sign_in_or_sign_out_in_another_tab_shows_on_an_open_account_page(self):
        self.open(390, 844, True)
        one = self.c.sid
        tid = self.c.call("Target.createTarget", {"url": "about:blank"}, browser=True)["targetId"]
        two = self.c.call("Target.attachToTarget", {"targetId": tid, "flatten": True}, browser=True)["sessionId"]
        try:
            self.c.sid = two
            self.c.call("Page.enable")
            self.c.call("Runtime.enable")
            view(self.c, 390, 844, True)
            self.open(390, 844, True)
            self.assertTrue(self.js(PANEL)["shown"])
            self.js("window.__stayed = true")
            # the first tab signs in: the second shows the shopper
            self.c.sid = one
            self.js("document.querySelector('[data-signin-go=\"\"]').click()")
            self.signed_in_here()
            self.c.sid = two
            until(self.c, "document.querySelector('[data-signin]').hidden", 10, what="the account in the second tab")
            me = self.js(ME)
            self.assertEqual((me["name"], me["email"], me["views"]), ("Noor Haddad", "noor@example.com", [False, False]))
            self.assertTrue(self.js(LINKS)["tab"]["signed"])
            # the first tab signs out: the second hides the name, email and menu and shows the panel
            self.c.sid = one
            self.js("document.querySelector('.acct-out').click()")
            until(self.c, "location.href === %s && %s" % (J(SITE + "/"), READY), 20, what="the home page")
            self.c.sid = two
            until(self.c, "!document.querySelector('[data-signin]').hidden", 10, what="the panel in the second tab")
            p = self.js(PANEL)
            self.assertEqual((p["shown"], p["views"], p["msg"]), (True, [True, True], ""))
            self.assertNotIn("Noor Haddad", p["text"])
            self.assertNotIn("noor@example.com", p["text"])
            self.assertFalse(self.js(LINKS)["tab"]["signed"])
            self.assertTrue(self.js("window.__stayed === true && location.href === %s" % J(SITE + "/account.html")),
                            "the second tab was not reloaded")
            self.no_errors()
        finally:
            self.c.sid = one

    # ---- the provider's address ----------------------------------------------------------
    def test_no_host_but_the_tests_own_is_reached_over_plain_http(self):
        self.open(1440, 900, False)
        tried = ["127.0.0.1:%d" % IDP_PORT, "example.com", "localhost:%d" % IDP_PORT, "http://example.com",
                 "https://example.com", "example.com:80", "127.0.0.1", "EXAMPLE.com", "example.com/x", "10.0.0.1:80"]
        got = self.js("""(() => { const was = window.BGS_AUTH, out = {};
          for (const d of %s) { window.BGS_AUTH = {domain: d, client_id: %s}; const a = bgsAuth(); out[d] = a && a.base; }
          window.BGS_AUTH = was; return out; })()""" % (J(tried), J(FAKE_CLIENT)))
        want = dict.fromkeys(tried)
        want.update({"127.0.0.1:%d" % IDP_PORT: "http://127.0.0.1:%d" % IDP_PORT, "example.com": "https://example.com"})
        self.assertEqual(got, want)
        # a catalogue naming another host that way: the page shows the account as a shop without sign-in does
        cat = BOX.repo / "flow" / "assets" / "catalogue.js"
        before = cat.read_bytes()
        try:
            other = ("window.BGS_AUTH = %s;" % J({"domain": "localhost:%d" % IDP_PORT, "client_id": FAKE_CLIENT})).encode()
            cat.write_bytes(re.sub(rb"^window\.BGS_AUTH = .*;$", other, before, flags=re.M))
            self.open(1440, 900, False)
            p = self.js(PANEL)
            self.assertEqual((p["shown"], p["views"]), (False, [False, False]))
            self.assertFalse(self.js(LINKS)["head"]["signed"])
        finally:
            cat.write_bytes(before)
        self.assertEqual(IDP.log, [], "nothing reached the provider")
        self.no_errors()


@unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
class RealTenantAddresses(unittest.TestCase):
    """Every place the shop is published signs in against the real tenant with
    a redirect_uri, web origin and returnTo from the application's lists in
    Auth0. The pages run at their real addresses inside Chrome (Browser), and
    the tenant's answers are made up there: nothing reaches Auth0."""

    @classmethod
    def setUpClass(cls):
        configure(TENANT, CLIENT)

    def token_answer(self, req):
        """Auth0's answer to a good code exchange, after checking it is one."""
        f = dict(urllib.parse.parse_qsl(req.get("postData") or ""))
        a = self.asked
        ok = (f.get("grant_type") == "authorization_code" and f.get("client_id") == CLIENT
              and f.get("code") == "code-from-auth0" and f.get("redirect_uri") == a["redirect_uri"]
              and b64url(hashlib.sha256(f.get("code_verifier", "").encode()).digest()) == a["code_challenge"])
        self.exchanges.append(ok)
        if not ok:
            return 403, {"error": "invalid_grant"}
        now = int(time.time())
        claims = {"iss": "https://%s/" % TENANT, "aud": CLIENT, "sub": "google-oauth2|1", "name": "Noor Haddad",
                  "email": "noor@example.com", "picture": "https://lh3.googleusercontent.com/a/noor", "iat": now,
                  "exp": now + 36000, "nonce": a["nonce"]}
        jwt = "%s.%s.c2ln" % (b64url(J({"alg": "RS256", "typ": "JWT"}).encode()), b64url(J(claims).encode()))
        return 200, {"access_token": "opaque", "id_token": jwt, "token_type": "Bearer", "expires_in": 86400}

    def walk(self, root, pretty, callback, logout):
        """From a product page to the account page by the header, sign in, come
        back, sign out: each address the shop used has to be on Auth0's lists."""
        page = lambda name: root + (name if pretty else name + ".html")  # noqa: E731
        b = Browser(1440, 900, False, BOX.repo / "flow")
        self.asked, self.exchanges = None, []
        b.token = self.token_answer
        try:
            start = page("product") + "?p=royal-amber"
            b.go(start)
            until(b, READY + " && location.href === %s" % J(start), 30, what=start)
            b.js("document.querySelector('.mast a.act-acct').click()")
            until(b, READY + " && location.href === %s" % J(page("account")), 20, what="the account page")
            b.js("document.querySelector('[data-signin-go=\"\"]').click()")
            until(b, "location.host === %s" % J(TENANT), 20, what="the tenant's /authorize")
            u = urllib.parse.urlsplit([s["url"] for s in b.seen if "/authorize?" in s["url"]][-1])
            self.asked = dict(urllib.parse.parse_qsl(u.query))
            self.assertEqual(u.path, "/authorize")
            self.assertEqual(self.asked["redirect_uri"], callback)
            self.assertIn(callback, CALLBACKS)
            self.assertEqual({k: self.asked.get(k) for k in ("client_id", "response_type", "scope", "code_challenge_method")},
                             {"client_id": CLIENT, "response_type": "code", "scope": "openid profile email",
                              "code_challenge_method": "S256"})

            # Auth0 sends the shopper back with a code, and the shop takes them back to the product
            b.go(callback + "?" + urllib.parse.urlencode({"code": "code-from-auth0", "state": self.asked["state"]}))
            until(b, READY + " && location.href === %s && !!document.querySelector('.mast a.act-acct.signed')" % J(start),
                  25, what="the product page, signed in")
            self.assertEqual(self.exchanges, [True], "the code went to the token endpoint with its verifier and redirect_uri")
            origin = [s for s in b.seen if s["url"].endswith("/oauth/token")][-1]["headers"].get("Origin")
            self.assertIn(origin, WEB_ORIGINS)
            self.assertEqual(b.js("JSON.parse(localStorage.getItem('bgs_profile')).name"), "Noor Haddad")

            # signing out from the account page goes through /v2/logout back to this site
            b.go(page("account"))
            until(b, READY + " && location.href === %s && !document.querySelector('.acct').hidden" % J(page("account")), 20)
            b.js("document.querySelector('.acctnav [data-signout]').click()")
            until(b, "location.host === %s && location.pathname === '/v2/logout'" % J(TENANT), 20, what="the tenant's /v2/logout")
            out = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit([s["url"] for s in b.seen if "/v2/logout?" in s["url"]][-1]).query))
            self.assertEqual((out.get("client_id"), out.get("returnTo")), (CLIENT, logout))
            self.assertIn(logout, LOGOUTS)
            b.go(logout)
            until(b, READY + " && location.href === %s" % J(logout), 20, what="the home page")
            self.assertIsNone(b.js("localStorage.getItem('bgs_profile')"))
            self.assertFalse(b.js("!!document.querySelector('.mast a.act-acct.signed')"))
            self.assertEqual(b.errors(), [])
            # the shop asked the tenant for these three and nothing else (Chrome asks the
            # stand-in page for its favicon.ico on its own)
            asked = [urllib.parse.urlsplit(s["url"]).path for s in b.seen]
            self.assertEqual(sorted(set(asked) - {"/favicon.ico"}), ["/authorize", "/oauth/token", "/v2/logout"], asked)
        finally:
            b.close()

    def test_github_pages_under_its_sub_path(self):
        root = "https://abdurrehmancatguy-gif.github.io/structured-corner-v2/"
        self.walk(root, False, root + "account.html", root)

    def test_netlify_with_its_pretty_urls(self):
        root = "https://enchanting-daffodil-aca9b0.netlify.app/"
        self.walk(root, True, root + "account", root)

    def test_the_shop_s_own_domain_with_and_without_www(self):
        for root in ("https://bgscorner.com/", "https://www.bgscorner.com/"):
            with self.subTest(root=root):
                self.walk(root, False, root + "account.html", root)


class SigninSettings(unittest.TestCase):
    """The two settings behind sign-in, as the admin keeps them."""

    @classmethod
    def setUpClass(cls):
        configure(TENANT, CLIENT)

    def settings(self):
        st, d = BOX.api("GET", "documents/settings")
        self.assertEqual(st, 200, d)
        return d["data"], d["rev"]

    def put_auth(self, **auth):
        data, rev = self.settings()
        data["auth"] = dict(data.get("auth") or {}, **auth)
        return BOX.api("PUT", "documents/settings", {"data": data}, rev=rev)

    def csp(self, path="/account.html"):
        return BOX.raw("GET", path)[1].get("Content-Security-Policy")

    def account(self):
        return (BOX.repo / "flow" / "account.html").read_text(encoding="utf-8")

    def test_settings_keep_the_domain_and_client_id_under_shopper_sign_in(self):
        st, s = BOX.api("GET", "schema")
        self.assertEqual(st, 200)
        fields = {f["path"]: f for f in s["resources"]["settings"]["fields"]}
        self.assertEqual([p for p in fields if p.startswith("/auth/")], ["/auth/domain", "/auth/client_id"],
                         "and none for a client secret")
        for p in ("/auth/domain", "/auth/client_id"):
            f = fields[p]
            self.assertEqual((f["group"], f["type"]), ("Shopper sign-in", "text"))
            self.assertTrue(f.get("help") and f.get("pattern") and f.get("patternHelp"), p)
            self.assertFalse(f.get("required"), "both may be left empty")
        self.assertEqual(self.settings()[0]["auth"], {"domain": TENANT, "client_id": CLIENT})
        self.assertEqual(global_in("BGS_AUTH"), {"domain": TENANT, "client_id": CLIENT})
        # the preview lets a store page reach the provider, and nothing else
        for path in ("/account.html", "/index.html", "/no-such-page"):
            self.assertEqual(self.csp(path), "connect-src https://" + TENANT, path)

    def test_bad_sign_in_settings_are_refused_and_nothing_changes(self):
        flow = BOX.repo / "flow"
        stored, built = (flow / "content" / "settings.json").read_bytes(), (flow / "assets" / "catalogue.js").read_bytes()
        for auth, path, code in (({"domain": "https://" + TENANT}, "/auth/domain", "format"),
                                 ({"domain": TENANT + "/"}, "/auth/domain", "format"),
                                 ({"domain": "127.0.0.1:%d" % IDP_PORT}, "/auth/domain", "format"),
                                 ({"domain": "Dev-I8cqekmfe57ladb2.us.auth0.com"}, "/auth/domain", "format"),
                                 ({"client_id": "s" * 64}, "/auth/client_id", "too_long"),
                                 ({"client_id": CLIENT[:-1] + "-"}, "/auth/client_id", "format"),
                                 ({"domain": ""}, "/auth/domain", "required"),
                                 ({"client_id": ""}, "/auth/client_id", "required")):
            st, res = self.put_auth(**auth)
            self.assertEqual(st, 422, (auth, res))
            self.assertIn((path, code), [(e["path"], e["code"]) for e in res["error"]["details"]], auth)
        self.assertEqual((flow / "content" / "settings.json").read_bytes(), stored)
        self.assertEqual((flow / "assets" / "catalogue.js").read_bytes(), built)

    def test_emptied_settings_hide_sign_in_and_the_preview_allows_no_calls(self):
        try:
            st, res = self.put_auth(domain="", client_id="")
            self.assertEqual(st, 200, res)
            self.assertIsNone(global_in("BGS_AUTH"))
            acct = self.account()
            for mark in ("data-signin", "data-acctview", "data-signout", "data-me="):
                self.assertNotIn(mark, acct)
            self.assertIn('<a href="index.html" class="out">Sign out</a>', acct)
            self.assertEqual(self.csp(), "connect-src 'none'")
        finally:
            st, res = self.put_auth(domain=TENANT, client_id=CLIENT)
            self.assertEqual(st, 200, res)
        self.assertEqual(global_in("BGS_AUTH"), {"domain": TENANT, "client_id": CLIENT})
        self.assertIn("data-signin", self.account())
        self.assertEqual(self.csp(), "connect-src https://" + TENANT)

    def test_the_build_stops_on_a_domain_it_would_reach_over_plain_http(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgssignin-"))
        try:
            flow = tmp / "flow"
            shutil.copytree(str(BOX.repo / "flow"), str(flow), ignore=shutil.ignore_patterns(".backups", "*.tmp"))
            built = (flow / "assets" / "catalogue.js").read_bytes()
            for auth, says in (({"domain": "http://example.com", "client_id": CLIENT}, "auth domain"),
                               ({"domain": "localhost:%d" % IDP_PORT, "client_id": CLIENT}, "auth domain"),
                               ({"domain": TENANT, "client_id": ""}, "auth client_id")):
                s = flow / "content" / "settings.json"
                d = json.loads(s.read_text(encoding="utf-8"))
                d["auth"] = auth
                s.write_text(json.dumps(d, indent=2), encoding="utf-8")
                p = subprocess.run([sys.executable, "build.py"], cwd=str(flow), capture_output=True, text=True, timeout=100)
                self.assertNotEqual(p.returncode, 0, auth)
                self.assertIn(says, p.stderr, auth)
                self.assertEqual((flow / "assets" / "catalogue.js").read_bytes(), built, "nothing is written")
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
