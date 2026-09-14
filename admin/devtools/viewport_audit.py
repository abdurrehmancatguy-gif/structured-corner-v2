#!/usr/bin/env python3
"""The storefront at every screen size: 28 viewports (portrait and landscape
phones, a folding phone, tablets, desktops and ultrawide) against 29 page
states, measured in headless Chrome and saved with a first-screen screenshot
of each. Standard library only; Chrome is driven over its DevTools pipe with
its own small client, modelled on admin/tests/cdp_pipe.py. Run it with
/usr/bin/python3.

    /usr/bin/python3 admin/devtools/viewport_audit.py list

    perl -e 'alarm shift; exec @ARGV' 110 /usr/bin/python3 admin/devtools/viewport_audit.py run \\
        --clone /path/to/clone --port 4970 --out /tmp/va [--viewports phones,844x390] \\
        [--pages cart,pdp-attar,ar] [--ar-viewports 320x568,390x844] [--min-font 12] \\
        [--min-font-desktop 11] [--max-crop 0.3] [--max-bar-share 0.3] [--workers 7] \\
        [--budget 72] [--full --full-screens 6] [--shot-scale 2] [--redo | --redo-errors] \\
        [--serve auto|storefront|http|none]

    /usr/bin/python3 admin/devtools/viewport_audit.py report --out /tmp/va [--min-font N] \\
        [--min-font-desktop N] [--max-bar-share F] [--top 30]

run works in batches that fit a two-minute limit: it starts the shop from
--clone (admin/server.py --storefront-only, or python -m http.server on its
flow/), spreads the jobs that have no result yet over --workers headless
Chrome processes, stops taking new jobs after --budget seconds, then stops
its server and every Chrome it started, also on SIGALRM, SIGTERM or Ctrl+C.
It exits 3 while jobs remain and 0 once none do, after writing the reports.
Repeat the same command until it exits 0. --redo runs the selection again
from the start (and stays idempotent across the repeated calls), and
--redo-errors only the jobs that ended in an error.

Phones are emulated at a device scale of 3 and tablets at 2, both as mobile
with touch (coarse pointer, no hover) and a mobile user agent; desktops at 1
with a mouse. Each job writes results/<state>__<WxH>.json and a screenshot of
the first screen, clipped to the visual viewport so it shows what the device
shows, at CSS-pixel size (--shot-scale 2 doubles it). --full also saves
<...>-full.jpg, up to --full-screens screens tall.

report rebuilds report.txt and report.json (issues grouped by type and
element, with pages, viewports, how much of each viewport group has them and
one example each), matrix.txt (high and medium counts per page and viewport,
and the worst cells with their screenshots) and checkout.txt (the bag's
Checkout per viewport, and the product page's Add to bag) from the saved
results, so thresholds can change without a rerun. Text is recorded below
14px, so --min-font works up to 14.

Checks: sideways scrolling, with the outermost element that causes it (and
content cut off where the page hides the scroll); text under the threshold,
naming inline font-size styles and skipping screen-reader-only text; form
fields under 16px (iOS zooms on focus); tap targets under 44 and under 24
(inline links marked, pseudo-element hit areas counted); fixed and sticky
bars' share of the screen once scrolled (full-height drawers ignored) and
bars overlapping each other; header and bars' share of the first screen;
primary actions covered, or outside the first screen; the bag's Checkout
reachable; images stretched, cropped by object-fit cover, drawn larger than
their file or broken; text clipped, spilling past its box or overlapping
other text; flex and grid boxes that drop the spaces around a child
("words-joined"); button labels that wrap; the tab bar on screen; the
language toggle visible; in Arabic, numbers and words drawn in swapped order,
arrows still pointing right and English left untranslated; script
exceptions and console errors, failed loads included.

Known limits: the first-screen furniture share counts the open filter
drawer in coll-filters (ignored there by the report). Full-page shots draw
fixed bars at their first-screen position and can show lazy images not yet
loaded.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
import pathlib
import queue
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# ---------------------------------------------------------------- the matrix
VIEWPORTS = [
    # portrait phones, the fold cover first
    ("280x653", "phones"), ("320x568", "phones"), ("360x640", "phones"), ("360x800", "phones"),
    ("375x667", "phones"), ("375x812", "phones"), ("390x844", "phones"), ("393x852", "phones"),
    ("412x915", "phones"), ("430x932", "phones"),
    # landscape phones
    ("568x320", "landscape"), ("667x375", "landscape"), ("844x390", "landscape"),
    ("915x412", "landscape"), ("932x430", "landscape"),
    # the fold open and portrait tablets, then landscape tablets
    ("673x841", "tablets"), ("600x960", "tablets"), ("768x1024", "tablets"), ("820x1180", "tablets"),
    ("1024x1366", "tablets"), ("1024x768", "tablets"), ("1180x820", "tablets"),
    # desktops and ultrawide
    ("1280x800", "desktops"), ("1366x768", "desktops"), ("1440x900", "desktops"),
    ("1920x1080", "desktops"), ("2560x1440", "desktops"), ("2560x1080", "desktops"),
]
GROUP = dict(VIEWPORTS)
GROUPS = ("phones", "landscape", "tablets", "desktops")
SETS = {g: [v for v, gg in VIEWPORTS if gg == g] for g in GROUPS}
SETS["touch"] = SETS["phones"] + SETS["landscape"] + SETS["tablets"]
SETS["all"] = [v for v, _ in VIEWPORTS]
DSF = {"phones": 3, "landscape": 3, "tablets": 2, "desktops": 1}
UA = {
    "phones": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/152.0.0.0 Mobile Safari/537.36",
    "tablets": "Mozilla/5.0 (Linux; Android 14; SM-X910) AppleWebKit/537.36 (KHTML, like Gecko) "
               "Chrome/152.0.0.0 Safari/537.36",
    "desktops": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/152.0.0.0 Safari/537.36",
}
UA["landscape"] = UA["phones"]

# four products and, over AED 300, the derived free gift's line: five lines
FIVE = [{"id": "royal-amber", "qty": 2}, {"id": "vibe", "qty": 1}, {"id": "bakhoor-1", "qty": 1},
        {"id": "discovery-trio", "qty": 1}]
PDP_ACTS = [("add", ".atcrow [data-add]", True), ("sticky", ".stickybuy [data-add]", False)]
CART_ACTS = [("checkout", "[data-cartsummary] [data-checkout]", True), ("bagbar", "[data-bagbar].on a", False)]
# name: path, what to do once loaded, the bag to start with, primary actions
# (key, selector, primary). Primary actions are checked for being covered.
STATES = {
    "index": {"path": "index.html", "acts": [("hero", ".hero .over.on .btn", True)]},
    "collection": {"path": "collection.html", "acts": [("card", "[data-grid] .p", True)]},
    "coll-attars": {"path": "collection.html?cat=attars", "acts": [("card", "[data-grid] .p", True)]},
    "coll-edp": {"path": "collection.html?cat=edp", "acts": [("card", "[data-grid] .p", True)]},
    "coll-bakhoor": {"path": "collection.html?cat=bakhoor", "acts": [("card", "[data-grid] .p", True)]},
    "coll-gifts": {"path": "collection.html?cat=gift-sets", "acts": [("card", "[data-grid] .p", True)]},
    "coll-q-oud": {"path": "collection.html?q=oud", "acts": [("card", "[data-grid] .p", True)]},
    "coll-filters": {"path": "collection.html", "do": "filters",
                     "acts": [("show", ".draweractions [data-closefilters]", True)]},
    "pdp-attar": {"path": "product.html?p=royal-amber", "acts": PDP_ACTS},
    "pdp-edp": {"path": "product.html?p=vibe", "acts": PDP_ACTS},
    "pdp-bakhoor": {"path": "product.html?p=bakhoor-1", "acts": PDP_ACTS},
    "pdp-gift": {"path": "product.html?p=eid-royal-hamper", "acts": PDP_ACTS},
    "pdp-long": {"path": "product.html?p=edward-the-black-prince", "acts": PDP_ACTS},
    "pdp-added": {"path": "product.html?p=vibe", "do": "add",
                  "acts": [("checkout", ".added.on .added-b a.solid", True)]},
    "gift-box": {"path": "gift-box.html", "acts": [("pick", ".two .grid.g4 .p [data-add]", True)]},
    "cart-empty": {"path": "cart.html", "cart": [], "acts": [("shop", "[data-cartempty] .btn", True)]},
    "cart-1": {"path": "cart.html", "cart": [{"id": "royal-amber", "qty": 1}], "acts": CART_ACTS},
    "cart-5": {"path": "cart.html", "cart": FIVE, "acts": CART_ACTS},
    "checkout": {"path": "checkout.html", "acts": [("place", 'a[href="confirmed.html"]', True)]},
    "confirmed": {"path": "confirmed.html", "acts": [("track", 'section a[href="track-order.html"]', True)]},
    "track-order": {"path": "track-order.html", "acts": [("find", "[data-findorder]", True)]},
    "account": {"path": "account.html", "acts": [("tab", ".acctnav a.on", True)]},
    "quiz": {"path": "quiz.html", "acts": [("answer", ".qcard:not([hidden]) .qopts button", True)]},
    "quiz-result": {"path": "quiz.html", "do": "quiz", "acts": [("see", "[data-rsee]", True)]},
    "corporate": {"path": "corporate.html", "acts": [("send", "[data-cqsend]", True)]},
    "404": {"path": "404.html", "acts": [("home", "#home", True)]},
    "ar-index": {"path": "index.html", "do": "ar", "ar": True, "acts": [("hero", ".hero .over.on .btn", True)]},
    "ar-pdp": {"path": "product.html?p=royal-amber", "do": "ar", "ar": True, "acts": PDP_ACTS},
    "ar-cart": {"path": "cart.html", "do": "ar", "ar": True, "cart": FIVE, "acts": CART_ACTS},
}
ALIASES = {
    "coll": [s for s in STATES if s == "collection" or s.startswith("coll-")],
    "pdp": [s for s in STATES if s.startswith("pdp-")],
    "cart": ["cart-empty", "cart-1", "cart-5"],
    "quiz": ["quiz", "quiz-result"],
    "ar": ["ar-index", "ar-pdp", "ar-cart"],
    "en": [s for s in STATES if not s.startswith("ar-")],
    "all": list(STATES),
}
AR_DEFAULT = "320x568,390x844"

# ------------------------------------------------------------ cleaning up
LIVE = []                      # every process this run started: Chrome and the server
LIVE_LOCK = threading.Lock()


def kill_all():
    with LIVE_LOCK:
        procs = list(LIVE)
        LIVE.clear()
    for p in procs:
        try:
            os.killpg(p.pid, signal.SIGKILL)        # started in its own session: helpers go too
        except (OSError, ProcessLookupError):
            pass
        try:
            p.wait(3)
        except Exception:
            pass


def on_signal(signum, _frame):
    kill_all()
    sys.stderr.write("stopped by signal %d; every Chrome and the server are stopped\n" % signum)
    os._exit(3)


# ------------------------------------------------------------ Chrome over its pipe
KEEP_EVENTS = ("Runtime.exceptionThrown", "Runtime.consoleAPICalled", "Log.entryAdded")


class Chrome:
    """One headless Chrome with one tab, driven over --remote-debugging-pipe."""

    def __init__(self, root):
        self.prof = tempfile.mkdtemp(prefix="va-prof-", dir=root)
        r_cmd, self.w = os.pipe()
        self.r, w_resp = os.pipe()
        hi_r = fcntl.fcntl(r_cmd, fcntl.F_DUPFD, 20)
        hi_w = fcntl.fcntl(w_resp, fcntl.F_DUPFD, 20)

        def child():
            os.setsid()
            os.dup2(hi_r, 3)
            os.dup2(hi_w, 4)

        self.p = subprocess.Popen(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             "--disable-extensions", "--disable-background-networking", "--disable-sync", "--mute-audio",
             "--hide-scrollbars", "--force-color-profile=srgb", "--disable-renderer-backgrounding",
             "--disable-background-timer-throttling", "--disable-backgrounding-occluded-windows",
             "--user-data-dir=" + self.prof, "--window-size=1400,1000", "--remote-debugging-pipe", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=child, close_fds=False)
        with LIVE_LOCK:
            LIVE.append(self.p)
        for fd in (r_cmd, w_resp, hi_r, hi_w):
            os.close(fd)
        self.buf, self.n, self.events, self.sid, self.script = b"", 0, [], None, None
        tid = self.call("Target.createTarget", {"url": "about:blank"}, browser=True)["targetId"]
        self.sid = self.call("Target.attachToTarget", {"targetId": tid, "flatten": True}, browser=True)["sessionId"]
        for m in ("Page.enable", "Runtime.enable", "Log.enable"):
            self.call(m)

    def _read(self, timeout):
        end = time.monotonic() + timeout
        while b"\0" not in self.buf:
            left = end - time.monotonic()
            if left <= 0:
                raise TimeoutError("Chrome did not answer")
            if select.select([self.r], [], [], left)[0]:
                chunk = os.read(self.r, 1 << 20)
                if not chunk:
                    raise RuntimeError("Chrome closed the pipe")
                self.buf += chunk
        msg, self.buf = self.buf.split(b"\0", 1)
        return json.loads(msg)

    def call(self, method, params=None, browser=False, timeout=20):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}}
        if not browser and self.sid:
            msg["sessionId"] = self.sid
        os.write(self.w, json.dumps(msg).encode() + b"\0")
        while True:
            m = self._read(timeout)
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError("%s: %s" % (method, m["error"]))
                return m.get("result", {})
            if m.get("method") in KEEP_EVENTS:
                self.events.append(m)

    def js(self, expr, timeout=20):
        r = self.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True,
                                           "userGesture": True}, timeout=timeout)
        if r.get("exceptionDetails"):
            raise RuntimeError("script failed: %s" % json.dumps(r["exceptionDetails"])[:500])
        return r.get("result", {}).get("value")

    def wait(self, expr, timeout=15):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            try:
                if self.js(expr):
                    return True
            except RuntimeError:
                pass                     # the old document went away mid-navigation
            time.sleep(0.08)
        return False

    def errors(self):
        out = []
        for e in self.events:
            m, p = e.get("method"), e.get("params", {})
            if m == "Runtime.exceptionThrown":
                d = p.get("exceptionDetails", {})
                out.append("exception: " + ((d.get("exception") or {}).get("description") or d.get("text") or "")[:300])
            elif m == "Runtime.consoleAPICalled" and p.get("type") == "error":
                out.append("console: " + " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))[:300])
            elif m == "Log.entryAdded" and p.get("entry", {}).get("level") == "error":
                en = p["entry"]
                out.append("log: %s %s" % (en.get("text", "")[:200], en.get("url", "")))
        return out

    def close(self):
        try:
            os.killpg(self.p.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        try:
            self.p.wait(5)
        except Exception:
            pass
        with LIVE_LOCK:
            if self.p in LIVE:
                LIVE.remove(self.p)
        for fd in (self.r, self.w):
            try:
                os.close(fd)
            except OSError:
                pass
        shutil.rmtree(self.prof, ignore_errors=True)


# ------------------------------------------------------------ the shop's server
def up(port):
    try:
        req = urllib.request.Request("http://127.0.0.1:%d/index.html" % port, headers={"Host": "localhost:%d" % port})
        return urllib.request.urlopen(req, timeout=2).status == 200
    except OSError:
        return False


def serve(mode, clone, port):
    """Start the shop on port from the clone; returns how it is served."""
    if mode == "none":
        if not up(port):
            sys.exit("--serve none, but nothing answers on port %d" % port)
        return "none"
    if up(port):
        sys.exit("port %d is taken already; pick a free one" % port)
    tries = ["storefront", "http"] if mode == "auto" else [mode]
    for how in tries:
        if how == "storefront":
            cmd = ["/usr/bin/python3", str(pathlib.Path(clone) / "admin" / "server.py"), "--storefront-only",
                   "--no-push", "--port", str(port), "--repo", str(clone)]
        else:
            cmd = ["/usr/bin/python3", "-m", "http.server", str(port), "--bind", "127.0.0.1",
                   "--directory", str(pathlib.Path(clone) / "flow")]
        if how == "storefront" and not (pathlib.Path(clone) / "admin" / "server.py").exists():
            continue
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        with LIVE_LOCK:
            LIVE.append(p)
        for _ in range(100):
            if up(port):
                return how
            if p.poll() is not None:
                break
            time.sleep(0.1)
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
        with LIVE_LOCK:
            if p in LIVE:
                LIVE.remove(p)
    sys.exit("the shop did not start on port %d" % port)


# ------------------------------------------------------------ in the page
# Shared helpers for the two measuring passes. sig() names an element by its
# tag, classes and nearest named ancestor, so one element type on many pages
# groups together; vis() is Chrome's own check (display, visibility, opacity
# of the element and its ancestors) plus a real box.
COMMON = r"""
  const de = document.documentElement, body = document.body, vv = window.visualViewport;
  const SKIP = /^(on|hidden|seen|open|anchored|js|done)$/;
  const AR = new RegExp('[' + String.fromCharCode(0x0600) + '-' + String.fromCharCode(0x06FF) + ']');
  const ARROW = new RegExp('[' + String.fromCharCode(0x2192, 0x203A) + ']');
  const one = (e) => {
    let s = e.tagName.toLowerCase();
    if (e.id && !/^bgs-/.test(e.id)) return s + '#' + e.id;
    const c = [...e.classList].filter((x) => !SKIP.test(x)).slice(0, 2);
    if (c.length) return s + '.' + c.join('.');
    const d = [...e.attributes].find((a) => a.name.startsWith('data-') && a.name !== 'data-was');
    return d ? s + '[' + d.name + ']' : s;
  };
  const sig = (e) => {
    if (!e || e.nodeType !== 1) return '';
    const parts = [one(e)];
    let p = e.parentElement, n = 0;
    while (p && p !== body && p !== de && n < 5) {
      const o = one(p);
      if (/[.#\[]/.test(o)) { parts.unshift(o); break; }
      p = p.parentElement; n++;
    }
    return parts.join(' ');
  };
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const short = (e) => clean(e.innerText !== undefined ? e.innerText : e.textContent).slice(0, 60);
  const vis = (e) => {
    if (!e || !e.isConnected) return false;
    if (e.checkVisibility && !e.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return false;
    const r = e.getBoundingClientRect();
    return r.width >= 1 && r.height >= 1;
  };
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const frames = () => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  const posOf = new Map();
  const fixedAnc = (e) => {
    const chain = []; let x = e, res = null;
    while (x && x.nodeType === 1 && x !== de) {
      if (posOf.has(x)) { res = posOf.get(x); break; }
      chain.push(x);
      if (getComputedStyle(x).position === 'fixed') { res = x; break; }
      x = x.parentElement;
    }
    for (const c of chain) posOf.set(c, res);
    return res;
  };
  const tabEl = document.querySelector('.tabbar');
  const tabOn = !!tabEl && vis(tabEl);
  const hit = (e) => {
    const r = e.getBoundingClientRect(), vw = de.clientWidth, ih = innerHeight;
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    if (x < 0 || y < 0 || x >= vw || y >= ih) return null;
    const h = document.elementFromPoint(x, y);
    if (!h) return null;
    return h === e || e.contains(h) ? 'ok' : sig(h);
  };
  const firstVis = (sel) => [...document.querySelectorAll(sel)].find(vis) || null;
  const bars = (skip) => {
    const res = [], ih = innerHeight;
    for (const e of body.querySelectorAll('*')) {
      const s = getComputedStyle(e);
      if (s.position !== 'fixed' && s.position !== 'sticky') continue;
      if (skip && e.matches(skip)) continue;
      if (!vis(e)) continue;
      const r = e.getBoundingClientRect();
      if (r.bottom <= 0 || r.top >= ih || r.height >= ih * 0.9) continue;
      if (s.position === 'sticky') { const t = parseFloat(s.top); if (!Number.isFinite(t) || Math.abs(r.top - t) > 1) continue; }
      if (s.pointerEvents === 'none') continue;
      let a = e.parentElement, inner = false;
      while (a && a !== body) { const ps = getComputedStyle(a).position; if (ps === 'fixed' || ps === 'sticky') { inner = true; break; } a = a.parentElement; }
      if (!inner) res.push({ e, r });
    }
    return res;
  };
  const cover = (items, extra) => {
    const ih = innerHeight;
    const iv = items.map((x) => [Math.max(0, x.r.top), Math.min(ih, x.r.bottom)]).concat(extra || [])
      .filter((x) => x[1] > x[0]).sort((a, b) => a[0] - b[0]);
    let tot = 0, cs = -1, ce = -1;
    for (const [a, b] of iv) { if (a > ce) { if (ce > cs) tot += ce - cs; cs = a; ce = b; } else ce = Math.max(ce, b); }
    if (ce > cs) tot += ce - cs;
    return tot;
  };
"""

# The first pass, on the page as it opened (or as its state left it): the
# layout checks that do not need a scroll. P carries W, H, DSF, maxCrop and
# acts, the state's actions as [key, selector, primary].
PASS_A = r"""
  const W = P.W, H = P.H, DSF = P.DSF, vw = de.clientWidth, ih = innerHeight;
  const out = { v: {}, texts: [], fields: [], taps: [], issues: [], acts: {}, rest: {}, tab: null, lang: null };
  const issue = (type, sev, e, detail) => out.issues.push({ type, sev, sig: e ? sig(e) : '', text: e ? short(e) : '', detail: detail || '' });
  const tabTop = tabOn ? tabEl.getBoundingClientRect().top : ih;
  out.v = { iw: innerWidth, ih, cw: vw, sw: de.scrollWidth, dh: de.scrollHeight, sy: Math.round(scrollY),
            vvw: vv ? vv.width : null, vvh: vv ? vv.height : null, scale: vv ? vv.scale : 1,
            dir: getComputedStyle(de).direction, lang: de.lang,
            coarse: matchMedia('(pointer:coarse)').matches, hoverNone: matchMedia('(hover:none)').matches,
            tabTop: tabOn ? Math.round(tabTop) : null };
  const all = [...body.querySelectorAll('*')].filter((e) => !(e.closest('svg') && e.tagName.toLowerCase() !== 'svg'));
  const V = (() => { const m = new Map(); return (e) => { if (!m.has(e)) m.set(e, vis(e)); return m.get(e); }; })();

  // ---- sideways: the outermost in-flow boxes past the screen's edge
  const lim = W + 0.5, off = [], fixedCut = [];
  for (const e of all) {
    const r = e.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const rtl = getComputedStyle(e).direction === 'rtl';
    if (!(r.right + scrollX > lim || (rtl && r.left + scrollX < -0.5))) continue;
    if (!V(e)) continue;
    const fx = fixedAnc(e);
    if (fx) {
      if (fx === e && r.bottom > 0 && r.top < ih && r.right > 0 && r.left < W && r.height < ih * 0.9) fixedCut.push(e);
      continue;
    }
    let a = e.parentElement, clipped = false;
    while (a && a !== body && a !== de) { if (getComputedStyle(a).overflowX !== 'visible') { clipped = true; break; } a = a.parentElement; }
    if (!clipped) off.push(e);
  }
  const offSet = new Set(off);
  const outer = off.filter((e) => { for (let a = e.parentElement; a && a !== body; a = a.parentElement) if (offSet.has(a)) return false; return true; });
  const wide = de.scrollWidth > lim || innerWidth > lim;
  if (wide) {
    if (!outer.length) issue('overflow', 'high', de, 'page ' + de.scrollWidth + 'px wide on a ' + W + 'px screen');
    outer.slice(0, 4).forEach((e) => issue('overflow', 'high', e, 'page ' + Math.max(de.scrollWidth, innerWidth) + 'px wide on a ' + W + 'px screen; this ends at ' + Math.round(e.getBoundingClientRect().right)));
  } else outer.slice(0, 4).forEach((e) => issue('cut-off', 'medium', e, 'ends at ' + Math.round(e.getBoundingClientRect().right) + ' on a ' + W + 'px screen'));
  fixedCut.slice(0, 3).forEach((e) => { const r = e.getBoundingClientRect(); issue('fixed-cut', 'medium', e, 'a fixed box from ' + Math.round(r.left) + ' to ' + Math.round(r.right) + ' on a ' + W + 'px screen'); });

  // ---- text: every visible text run, its size, and its line boxes
  const texts = new Map(), parents = new Map(), runs = [];
  const tw = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
  for (let n = tw.nextNode(); n; n = tw.nextNode()) {
    const t = n.nodeValue;
    if (!t || !t.trim()) continue;
    const p = n.parentElement;
    if (!p || /^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|OPTION|TITLE)$/.test(p.tagName)) continue;
    if (!V(p) || p.closest('.none-visual')) continue;
    const rg = document.createRange(); rg.selectNodeContents(n);
    const rr = rg.getBoundingClientRect();
    if (rr.width < 1 || rr.height < 1 || rr.right <= 0 || rr.left >= vw) continue;
    const fx = fixedAnc(p);
    if (fx && (rr.bottom <= 0 || rr.top >= ih)) continue;
    runs.push({ n, p, fixed: !!fx });
    const u = parents.get(p) || { l: 1e9, t: 1e9, r: -1e9, b: -1e9, fixed: !!fx, lines: [] };
    u.l = Math.min(u.l, rr.left); u.t = Math.min(u.t, rr.top); u.r = Math.max(u.r, rr.right); u.b = Math.max(u.b, rr.bottom);
    for (const q of rg.getClientRects()) if (q.width >= 1) u.lines.push([q.left, q.top, q.right, q.bottom]);
    parents.set(p, u);
    const fs = parseFloat(getComputedStyle(p).fontSize);
    if (fs < 14) {
      const k = sig(p) + '|' + fs, cur = texts.get(k);
      if (cur) cur.n++;
      else {
        let inl = null;
        for (let x = p; x && x !== body; x = x.parentElement) {
          if (x.style && x.style.fontSize) { if (Math.abs(parseFloat(getComputedStyle(x).fontSize) - fs) < 0.01) inl = sig(x); break; }
        }
        texts.set(k, { sig: sig(p), fs, n: 1, text: clean(t).slice(0, 50), inline: inl, fixed: !!fx });
      }
    }
  }
  out.texts = [...texts.values()];

  // ---- form fields: under 16px, iOS zooms the page when one takes focus
  for (const f of document.querySelectorAll('input,select,textarea')) {
    const ty = (f.getAttribute('type') || 'text').toLowerCase();
    if (/^(checkbox|radio|hidden|submit|button|image|range|color|file|reset)$/.test(ty) || !V(f)) continue;
    const r = f.getBoundingClientRect();
    if (r.right <= 0 || r.left >= vw) continue;
    out.fields.push({ sig: sig(f), fs: parseFloat(getComputedStyle(f).fontSize) });
  }

  // ---- tap targets: the box, a wrapping label, or an absolute ::before/::after
  const taps = new Map();
  const TAP = 'a[href],button,input:not([type=hidden]),select,textarea,summary,[role=button],[tabindex]:not([tabindex="-1"])';
  for (const e of document.querySelectorAll(TAP)) {
    if (!V(e) || e.closest('.none-visual')) continue;
    if (e.matches('input[type=checkbox],input[type=radio]') && e.closest('label')) continue;
    const r = e.getBoundingClientRect();
    if (r.right <= 0 || r.left >= vw) continue;
    const fx = fixedAnc(e);
    if (fx && (r.bottom <= 0 || r.top >= ih)) continue;
    let w = r.width, h = r.height;
    const lab = e.closest('label');
    if (lab) { const lr = lab.getBoundingClientRect(); w = Math.max(w, lr.width); h = Math.max(h, lr.height); }
    if (getComputedStyle(e).position !== 'static') {
      for (const pe of ['::before', '::after']) {
        const ps = getComputedStyle(e, pe);
        if (ps.content === 'none' || ps.content === 'normal' || ps.position !== 'absolute' || ps.display === 'none') continue;
        const t = parseFloat(ps.top), b = parseFloat(ps.bottom), l = parseFloat(ps.left), rt = parseFloat(ps.right);
        if ([t, b, l, rt].every(Number.isFinite)) { w = Math.max(w, r.width - l - rt); h = Math.max(h, r.height - t - b); }
      }
    }
    if (Math.min(w, h) >= 44) continue;
    let inline = false;
    if (e.tagName === 'A' && getComputedStyle(e).display === 'inline' && e.parentElement)
      inline = [...e.parentElement.childNodes].some((k) => k !== e && k.nodeType === 3 && k.nodeValue.trim());
    const k = sig(e), cur = taps.get(k);
    if (cur) { cur.n++; if (Math.min(w, h) < Math.min(cur.w, cur.h)) { cur.w = Math.round(w); cur.h = Math.round(h); } }
    else taps.set(k, { sig: k, w: Math.round(w), h: Math.round(h), n: 1, text: short(e).slice(0, 30), inline });
  }
  out.taps = [...taps.values()];

  // ---- text spilling past its box, clipped by it, or drawn over other text
  let spills = 0, clips = 0, ovs = 0;
  const lines = [];
  for (const [p, u] of parents) {
    const s = getComputedStyle(p), r = p.getBoundingClientRect();
    if (s.display !== 'inline' && s.display !== 'contents') {
      const bl = parseFloat(s.borderLeftWidth) || 0, br = parseFloat(s.borderRightWidth) || 0;
      if (s.overflowX !== 'visible') {
        if (p.clientWidth > 0 && p.scrollWidth > p.clientWidth + 1 && s.textOverflow !== 'ellipsis' && clips++ < 12)
          issue('text-clipped', 'medium', p, 'content ' + p.scrollWidth + 'px in ' + p.clientWidth + 'px');
      } else if ((u.r > r.right - br + 1.5 || u.l < r.left + bl - 1.5) && spills++ < 12)
        issue('text-spill', 'medium', p, 'text from ' + Math.round(u.l) + ' to ' + Math.round(u.r) + ' in a box from ' + Math.round(r.left + bl) + ' to ' + Math.round(r.right - br));
    }
    if (!u.fixed) for (const q of u.lines) lines.push({ p, l: q[0], t: q[1], r: q[2], b: q[3] });
  }
  lines.sort((a, b) => a.t - b.t);
  const seenPair = new Set();
  for (let i = 0; i < lines.length && ovs < 8; i++) {
    const a = lines[i];
    for (let j = i + 1; j < lines.length && lines[j].t < a.b - 1; j++) {
      const b = lines[j];
      if (a.p === b.p) continue;
      const ox = Math.min(a.r, b.r) - Math.max(a.l, b.l), oy = Math.min(a.b, b.b) - Math.max(a.t, b.t);
      if (ox <= 1 || oy <= 2) continue;
      if (a.p.contains(b.p) || b.p.contains(a.p)) continue;
      if (ox * oy < 0.25 * Math.min((a.r - a.l) * (a.b - a.t), (b.r - b.l) * (b.b - b.t))) continue;
      const key = sig(a.p) + '|' + sig(b.p);
      if (seenPair.has(key)) continue;
      seenPair.add(key);
      issue('text-overlap', 'medium', a.p, 'drawn over ' + sig(b.p) + ' "' + short(b.p).slice(0, 30) + '"');
      ovs++;
    }
  }

  // ---- flex and grid boxes drop the space at the edge of a text run
  let joined = 0;
  for (const e of all) {
    const s = getComputedStyle(e);
    if (!/flex|grid/.test(s.display) || (parseFloat(s.columnGap) || 0) > 0) continue;
    const ks = e.childNodes;
    if (![...ks].some((k) => k.nodeType === 3 && k.nodeValue.trim()) || !V(e)) continue;
    const shown = (x) => !!x && x.nodeType === 1 && getComputedStyle(x).display !== 'none';
    for (const k of ks) {
      if (k.nodeType !== 3 || !k.nodeValue.trim()) continue;
      if ((/\s$/.test(k.nodeValue) && shown(k.nextSibling)) || (/^\s/.test(k.nodeValue) && shown(k.previousSibling))) {
        if (joined++ < 10) issue('words-joined', 'high', e, 'the space beside "' + clean(k.nodeValue).slice(0, 30) + '" is dropped');
        break;
      }
    }
  }

  // ---- button and chip labels on more than one line
  let wraps = 0;
  for (const e of document.querySelectorAll('button,.btn,.pill,.catnav a,.tabbar a,.acctnav a,.added-b a')) {
    if (!V(e)) continue;
    const r = e.getBoundingClientRect();
    if (r.right <= 0 || r.left >= vw) continue;
    const fx = fixedAnc(e);
    if (fx && (r.bottom <= 0 || r.top >= ih)) continue;
    const ls = [], w2 = document.createTreeWalker(e, NodeFilter.SHOW_TEXT);
    for (let n = w2.nextNode(); n; n = w2.nextNode()) {
      if (!n.nodeValue.trim() || !V(n.parentElement) || n.parentElement.closest('.none-visual')) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      for (const q of rg.getClientRects()) {
        if (q.width < 1) continue;
        const m = ls.find((L) => q.top < L[1] - 1 && q.bottom > L[0] + 1);
        if (m) { m[0] = Math.min(m[0], q.top); m[1] = Math.max(m[1], q.bottom); } else ls.push([q.top, q.bottom]);
      }
    }
    if (ls.length > 1 && wraps++ < 15) issue('label-wraps', 'low', e, ls.length + ' lines in ' + Math.round(r.width) + 'px');
  }

  // ---- the tab bar on screen, and the language toggle there to press
  if (tabEl) {
    const r = tabEl.getBoundingClientRect(), bottom = vv ? vv.offsetTop + vv.height : ih;
    out.tab = { on: tabOn, top: Math.round(r.top), bottom: Math.round(r.bottom), h: Math.round(r.height) };
    if (W <= 900 && !tabOn) issue('tabbar-missing', 'high', tabEl, 'no tab bar at ' + W + 'px');
    if (tabOn && (r.bottom > bottom + 1.5 || r.top >= bottom)) issue('tabbar-offscreen', 'high', tabEl, 'bottom ' + Math.round(r.bottom) + ' on a ' + Math.round(bottom) + 'px screen');
  }
  const lt = document.querySelector('[data-langtoggle]');
  if (lt) {
    const r = lt.getBoundingClientRect(), ok = vis(lt) && r.right > 0 && r.left < vw;
    out.lang = { visible: ok, w: Math.round(r.width), h: Math.round(r.height) };
    if (!ok) issue('lang-toggle-hidden', 'high', lt, 'the only language toggle is not visible');
  }

  // ---- Arabic: order, arrows and what is still English
  if (out.v.dir === 'rtl') {
    let ord = 0, arr = 0;
    const unt = new Map();
    out.untranslated = 0;
    for (const { n, p } of runs) {
      const s = n.nodeValue, t = s.trim(), ps = getComputedStyle(p);
      if (ps.direction === 'rtl' && /^[A-Za-z0-9]/.test(t) && !AR.test(t) && /[^A-Za-z0-9]/.test(t)) {
        let i0 = 0, i1 = s.length - 1;
        while (i0 < s.length && /\s/.test(s[i0])) i0++;
        while (i1 > 0 && /\s/.test(s[i1])) i1--;
        const a = document.createRange(); a.setStart(n, i0); a.setEnd(n, i0 + 1);
        const b = document.createRange(); b.setStart(n, i1); b.setEnd(n, i1 + 1);
        const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
        if (ra.width && rb.width && Math.abs(ra.top - rb.top) < 3 && ra.left > rb.left + 0.5 && ord++ < 20)
          issue('rtl-order', 'high', p, '"' + clean(t).slice(0, 40) + '" drawn with its first character right of its last');
      }
      if (ARROW.test(t) && ps.direction === 'rtl') {
        let x = p, flipped = false;
        for (let d = 0; d < 3 && x && x !== body; d++, x = x.parentElement) {
          const m = getComputedStyle(x).transform.match(/matrix\(([^,]+)/);
          if (m && parseFloat(m[1]) < 0) { flipped = true; break; }
        }
        if (!flipped && arr++ < 10) issue('rtl-arrow', 'medium', p, 'an arrow still points right: "' + clean(t).slice(0, 30) + '"');
      }
      if (/[A-Za-z]{3,}/.test(t) && !AR.test(t) && !p.closest('[data-langtoggle]')) {
        out.untranslated++;
        const k = sig(p), u = unt.get(k);
        if (u) u.n++; else unt.set(k, { n: 1, text: clean(t).slice(0, 40), p });
      }
    }
    [...unt.values()].sort((a, b) => b.n - a.n).slice(0, 12)
      .forEach((u) => issue('rtl-untranslated', 'low', u.p, u.n + ' run(s) in English, e.g. "' + u.text + '"'));
  }

  // ---- the first screen: header and bars, and each action's place
  let hb = 0;
  for (const sel of ['.strip', '.mast', '.msearch', '.catnav']) {
    const e = document.querySelector(sel);
    if (e && vis(e)) { const r = e.getBoundingClientRect(); if (r.top < ih && r.bottom > 0) hb = Math.max(hb, Math.min(ih, r.bottom)); }
  }
  const rest = bars('.added,.added *,.scrim');
  out.rest = { header: Math.round(hb), share: +(cover(rest, [[0, hb]]) / ih).toFixed(3),
               bars: rest.map((x) => ({ sig: sig(x.e), top: Math.round(x.r.top), bottom: Math.round(x.r.bottom) })) };
  const usable = Math.min(ih, tabTop);
  for (const [key, sel, primary] of P.acts) {
    const el = firstVis(sel);
    if (!el) { out.acts[key] = { found: false, primary }; continue; }
    const r = el.getBoundingClientRect();
    out.acts[key] = { found: true, primary, sig: sig(el), text: short(el).slice(0, 40), top: Math.round(r.top), bottom: Math.round(r.bottom),
      w: Math.round(r.width), h: Math.round(r.height), onScreen: r.bottom > 0 && r.top < ih,
      inFirst: r.top >= -0.5 && r.bottom <= usable + 0.5 && r.left >= -0.5 && r.right <= vw + 0.5, hit0: hit(el) };
  }

  // ---- pictures: broken, stretched, cropped, or drawn past their file's pixels
  const fileW = new Map();
  const fw = (url) => {
    if (!fileW.has(url)) fileW.set(url, new Promise((res) => {
      const im = new Image(); im.onload = () => res(im.naturalWidth); im.onerror = () => res(0);
      setTimeout(() => res(0), 3000); im.src = url;
    }));
    return fileW.get(url);
  };
  const pics = [];
  for (const im of document.images) {
    if (!V(im)) continue;
    const r = im.getBoundingClientRect();
    if (r.right <= 0 || r.left >= vw || !im.complete) continue;
    const src = im.currentSrc || im.src;
    if (!src) continue;
    const name = src.split('/').pop().split('?')[0];
    if (!im.naturalWidth) { issue('image-broken', 'high', im, name); continue; }
    pics.push({ im, r, src, name, file: fw(src) });
  }
  let crops = 0, ups = 0, str = 0;
  for (const x of pics) {
    const s = getComputedStyle(x.im), fit = s.objectFit, r = x.r;
    const ir = x.im.naturalWidth / x.im.naturalHeight, br = r.width / r.height;
    if (fit === 'fill' && Math.abs(br / ir - 1) > 0.03 && str++ < 10)
      issue('image-stretched', 'medium', x.im, Math.round(Math.abs(br / ir - 1) * 100) + '% out of shape (' + x.name + ')');
    if (fit === 'cover') {
      const crop = 1 - Math.min(br / ir, ir / br);
      if (crop > P.maxCrop && crops++ < 10) issue('image-cropped', 'low', x.im, Math.round(crop * 100) + '% cut away (' + x.name + ')');
    }
    const file = await x.file;
    if (file) {
      const drawn = fit === 'cover' ? Math.max(r.width, r.height * ir)
        : (fit === 'contain' || fit === 'scale-down') ? Math.min(r.width, r.height * ir) : r.width;
      const up = drawn * DSF / file;
      if (up > 1.25 && ups++ < 12) issue('image-upscaled', 'low', x.im, up.toFixed(2) + 'x: a ' + file + 'px file drawn ' + Math.round(drawn * DSF) + ' device px wide (' + x.name + ')');
    }
  }
  return out;
"""

# The second pass: each action scrolled to the middle of the screen and hit
# tested there, then the bars once the page is scrolled 40% of the way down.
PASS_B = r"""
  const out = { acts: {}, bars: null }, ih = innerHeight;
  for (const [key, sel] of P.acts) {
    const el = firstVis(sel);
    if (!el) continue;
    if (!fixedAnc(el)) { el.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'instant' }); await frames(); await sleep(280); }
    out.acts[key] = { hit1: hit(el), top1: Math.round(el.getBoundingClientRect().top) };
  }
  scrollTo({ top: Math.max(0, (de.scrollHeight - ih) * 0.4), behavior: 'instant' });
  await frames(); await sleep(450);
  const b = bars('.added,.added *,.scrim'), overlaps = [];
  for (let i = 0; i < b.length; i++) for (let j = i + 1; j < b.length; j++) {
    const x = b[i].r, y = b[j].r;
    const ox = Math.min(x.right, y.right) - Math.max(x.left, y.left), oy = Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top);
    if (ox > 2 && oy > 2) overlaps.push(sig(b[i].e) + ' / ' + sig(b[j].e) + ': ' + Math.round(oy) + 'px');
  }
  out.bars = { sy: Math.round(scrollY), share: +(cover(b) / ih).toFixed(3), overlaps,
               items: b.map((x) => ({ sig: sig(x.e), top: Math.round(x.r.top), bottom: Math.round(x.r.bottom) })) };
  scrollTo({ top: 0, behavior: 'instant' });
  await frames(); await sleep(200);
  return out;
"""

# fonts, the pictures on the first screen (2.5 s at most), two frames, a breath
SETTLE = r"""(async () => {
  try { await Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 1500))]); } catch (e) {}
  const ih = innerHeight;
  const pend = [...document.images].filter((i) => { const r = i.getBoundingClientRect(); return !i.complete && r.top < ih && r.bottom > 0; });
  await Promise.race([Promise.all(pend.map((i) => new Promise((r) => { i.addEventListener('load', r, { once: true }); i.addEventListener('error', r, { once: true }); }))),
                      new Promise((r) => setTimeout(r, 2500))]);
  await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
  await new Promise((r) => setTimeout(r, 250));
  return true;
})()"""

# where to press Add to bag on a product page: the inline button when it is
# on the first screen, else the sticky bar's, else the inline one scrolled to
ADD_POINT = r"""(() => {
  const ok = (e) => !!e && e.checkVisibility() && e.getBoundingClientRect().width > 0;
  const tab = document.querySelector('.tabbar');
  const tabTop = tab && getComputedStyle(tab).display !== 'none' ? tab.getBoundingClientRect().top : innerHeight;
  const inl = document.querySelector('.atcrow [data-add]'), st = document.querySelector('.stickybuy:not(.hidden) [data-add]');
  let e = null, how = '';
  if (ok(inl)) { const r = inl.getBoundingClientRect(); if (r.top >= 0 && r.bottom <= tabTop) { e = inl; how = 'inline'; } }
  if (!e && ok(st)) { const r = st.getBoundingClientRect(); if (r.top >= 0 && r.bottom <= innerHeight) { e = st; how = 'sticky'; } }
  if (!e && inl) { inl.scrollIntoView({ block: 'center', behavior: 'instant' }); e = inl; how = 'inline, scrolled to'; }
  if (!e) return null;
  const r = e.getBoundingClientRect(), v = visualViewport, s = v ? v.scale : 1;
  window.__vaBtn = e;
  return { how, x: (r.left + r.width / 2 - (v ? v.offsetLeft : 0)) * s, y: (r.top + r.height / 2 - (v ? v.offsetTop : 0)) * s };
})()"""
AFTER_ADD = r"""(() => { const b = window.__vaBtn, p = document.querySelector('.added'), n = document.querySelector('[data-bagcount]');
  return { label: b ? b.textContent.trim() : null, panel: !!p && !p.hidden && p.classList.contains('on'), badge: n ? n.textContent : null }; })()"""


def page_fn(body, params):
    return "(async (P) => {\n" + COMMON + body + "\n})(" + json.dumps(params) + ")"


def emulate(c, vp):
    w, h = (int(x) for x in vp.split("x"))
    g = GROUP[vp]
    touch, dsf = g != "desktops", DSF[g]
    c.call("Emulation.setDeviceMetricsOverride", {
        "width": w, "height": h, "deviceScaleFactor": dsf, "mobile": touch, "screenWidth": w, "screenHeight": h,
        "positionX": 0, "positionY": 0,
        "screenOrientation": {"type": "portraitPrimary", "angle": 0} if h >= w else {"type": "landscapePrimary", "angle": 90}})
    c.call("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5} if touch else {"enabled": False})
    c.call("Emulation.setUserAgentOverride", {"userAgent": UA[g]})
    return w, h, dsf, touch


def prime(c, cart):
    """The bag (and an empty wishlist) in place before any of the page's scripts run."""
    if c.script:
        c.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": c.script})
    src = "try{localStorage.setItem('bgs_cart',%s);localStorage.setItem('bgs_wish','[]')}catch(e){}" % json.dumps(json.dumps(cart))
    c.script = c.call("Page.addScriptToEvaluateOnNewDocument", {"source": src})["identifier"]


def open_page(c, url):
    try:
        c.js("window.__vaOld = 1")
    except RuntimeError:
        pass
    c.events = []
    c.call("Page.navigate", {"url": url})
    if not c.wait("!window.__vaOld && document.readyState === 'complete'", 25):
        raise TimeoutError("the page did not load: " + url)
    c.js(SETTLE, timeout=15)


def press(c, x, y):
    for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
        c.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})


def do_state(c, st, res):
    act = st.get("do")
    if act == "filters":
        res["did"] = c.js("(() => { const b = document.querySelector('[data-openfilters]'); if (!b) return false; b.click(); "
                          "return document.body.classList.contains('filters-open'); })()")
        time.sleep(0.45)
    elif act == "quiz":
        for _ in range(12):
            if c.js("(() => { const r = document.querySelector('[data-qresult]'); if (r && !r.hidden) return true; "
                    "const b = document.querySelector('.qcard:not([hidden]) .qopts button'); if (b) b.click(); return false; })()"):
                res["did"] = True
                break
            time.sleep(0.2)
        c.js("scrollTo(0, 0)")
        time.sleep(0.3)
    elif act == "ar":
        res["did"] = c.js("(() => { const t = document.querySelector('[data-langtoggle]'); if (!t) return null; "
                          "const r = t.getBoundingClientRect(), shown = t.checkVisibility() && r.width > 0 && r.height > 0; "
                          "t.click(); return { shown, dir: document.documentElement.dir }; })()")
        time.sleep(0.35)
    elif act == "add":
        pt = c.js(ADD_POINT)
        if pt:
            time.sleep(0.15)
            press(c, pt["x"], pt["y"])
            time.sleep(0.4)
            res["did"] = dict(pt, after=c.js(AFTER_ADD))


def shot(c, path, scale, dsf, full=False, screens=6):
    m = c.js("(() => { const v = visualViewport; return { x: v.pageLeft, y: v.pageTop, w: v.width, h: v.height, "
             "dh: document.documentElement.scrollHeight, iw: innerWidth }; })()")
    if full:
        clip = {"x": 0, "y": 0, "width": m["iw"], "height": min(m["dh"], m["h"] * screens), "scale": scale / dsf}
    else:
        clip = {"x": m["x"], "y": m["y"], "width": m["w"], "height": m["h"], "scale": scale / dsf}
    r = c.call("Page.captureScreenshot", {"format": "jpeg", "quality": 70, "clip": clip,
                                          "captureBeyondViewport": bool(full)}, timeout=40)
    path.write_bytes(base64.b64decode(r["data"]))


def iss(t, sev, x, detail):
    return {"type": t, "sev": sev, "sig": (x or {}).get("sig", ""), "text": (x or {}).get("text", ""), "detail": detail}


def judge(acts, bars):
    """The primary actions: covered once scrolled into view, or with nothing
    standing in for them. A bag has its Checkout on the first screen or the
    checkout bar; a product page its Add to bag or the sticky bar; after an
    Add, the panel's Checkout."""
    out = []

    def ok(x):
        return bool(x and x.get("found") and x.get("onScreen") and x.get("hit0") == "ok")

    for x in acts.values():
        if x.get("found") and x.get("primary") and x.get("hit1") not in (None, "ok"):
            out.append(iss("action-covered", "high", x, "covered by %s once scrolled into view" % x["hit1"]))
    if "bagbar" in acts:
        c, b = acts.get("checkout", {}), acts.get("bagbar", {})
        if c.get("found") and not ((c.get("inFirst") and c.get("hit0") == "ok") or ok(b)):
            out.append(iss("checkout-unreachable", "high", c, "no Checkout on the first screen and no checkout bar"))
    elif "sticky" in acts:
        a, s = acts.get("add", {}), acts.get("sticky", {})
        if a.get("found") and not ((a.get("inFirst") and a.get("hit0") == "ok") or ok(s)):
            out.append(iss("add-unreachable", "high", a, "Add to bag neither on the first screen nor in the sticky bar"))
    elif set(acts) == {"checkout"}:
        if not ok(acts["checkout"]):
            out.append(iss("added-checkout-missing", "high", acts["checkout"], "no Checkout in sight after Add to bag"))
    else:
        for x in acts.values():
            if x.get("primary") and x.get("found") and x.get("inFirst") and x.get("hit0") not in (None, "ok"):
                out.append(iss("action-covered", "high", x, "covered on the first screen by %s" % x["hit0"]))
    for o in (bars or {}).get("overlaps", []):
        out.append({"type": "bar-overlap", "sev": "medium", "sig": o.split(":")[0], "text": "", "detail": o})
    return out


def run_job(c, job, a, base, out):
    state, vp = job
    st = STATES[state]
    t0 = time.monotonic()
    w, h, dsf, touch = emulate(c, vp)
    prime(c, st.get("cart", []))
    open_page(c, base + st["path"])
    res = {"state": state, "vp": vp, "w": w, "h": h, "dsf": dsf, "group": GROUP[vp], "touch": touch, "url": st["path"]}
    do_state(c, st, res)
    name = "%s__%s" % job
    params = {"W": w, "H": h, "DSF": dsf, "maxCrop": a.max_crop, "acts": [list(x) for x in st["acts"]]}
    first = st.get("do") == "add"          # the moment after the press, before the label goes back
    if first:
        shot(c, out / "shots" / (name + ".jpg"), a.shot_scale, dsf)
    A = c.js(page_fn(PASS_A, params), timeout=40)
    if not first:
        shot(c, out / "shots" / (name + ".jpg"), a.shot_scale, dsf)
    B = c.js(page_fn(PASS_B, params), timeout=40)
    for k, v in (B.get("acts") or {}).items():
        if k in A["acts"]:
            A["acts"][k].update(v)
    res.update({k: A.get(k) for k in ("v", "texts", "fields", "taps", "rest", "tab", "lang", "acts", "untranslated")})
    res["bars"] = B.get("bars")
    issues = A["issues"] + judge(A["acts"], B.get("bars"))
    if a.full:
        shot(c, out / "shots" / (name + "-full.jpg"), a.shot_scale, dsf, full=True, screens=a.full_screens)
    errs = list(dict.fromkeys(c.errors()))
    issues += [{"type": "js-error", "sev": "high", "sig": "", "text": "", "detail": e} for e in errs[:8]]
    res.update(errors=errs, issues=issues, shot="shots/%s.jpg" % name, secs=round(time.monotonic() - t0, 2))
    return res

# ------------------------------------------------------------ the matrix, in batches
def parse_vps(spec):
    out = []
    for part in (spec or "all").split(","):
        part = part.strip()
        if not part:
            continue
        if part in SETS:
            out += SETS[part]
        elif part in GROUP:
            out.append(part)
        else:
            sys.exit("unknown viewport or set: %s (see: list)" % part)
    return list(dict.fromkeys(out))


def parse_states(spec):
    out = []
    for part in (spec or "all").split(","):
        part = part.strip()
        if not part:
            continue
        if part in ALIASES:
            out += ALIASES[part]
        elif part in STATES:
            out.append(part)
        else:
            sys.exit("unknown page state: %s (see: list)" % part)
    return list(dict.fromkeys(out))


def select_jobs(a):
    """In matrix order, a viewport's states together. Arabic states run on
    --ar-viewports, whatever --viewports says."""
    vps, ar_vps, states = set(parse_vps(a.viewports)), set(parse_vps(a.ar_viewports)), parse_states(a.pages)
    return [(s, v) for v, _ in VIEWPORTS for s in states if (v in ar_vps if s.startswith("ar-") else v in vps)]


def result_path(out, job):
    return out / "results" / ("%s__%s.json" % job)


def pending(a, out, jobs):
    """Jobs with no result yet. With --redo or --redo-errors, a marker keeps
    the time the redo started, so the repeated calls finish it instead of
    starting it over."""
    marker, since = None, 0.0
    if a.redo or a.redo_errors:
        key = hashlib.md5(json.dumps([sorted(jobs), bool(a.redo)]).encode()).hexdigest()[:10]
        marker = out / (".redo-" + key)
        if not marker.exists():
            marker.write_text(str(time.time()))
        since = float(marker.read_text() or 0)
    left = []
    for j in jobs:
        p = result_path(out, j)
        if not p.exists():
            left.append(j)
        elif marker is not None and p.stat().st_mtime < since:
            if a.redo:
                left.append(j)
            else:
                try:
                    if "error" in json.loads(p.read_text()):
                        left.append(j)
                except ValueError:
                    left.append(j)
    return left, marker


def save(out, res):
    p = result_path(out, (res["state"], res["vp"]))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, ensure_ascii=False))
    os.replace(str(tmp), str(p))


def worker(q, a, base, out, root, deadline, stats, lock):
    c = None
    try:
        while time.monotonic() < deadline:
            try:
                job = q.get_nowait()
            except queue.Empty:
                return
            res = None
            for _attempt in (1, 2):
                try:
                    if c is None:
                        c = Chrome(root)
                    res = run_job(c, job, a, base, out)
                    break
                except Exception as e:          # a fresh Chrome gets one more go
                    if c:
                        c.close()
                        c = None
                    res = {"state": job[0], "vp": job[1], "group": GROUP[job[1]], "issues": [],
                           "error": "%s: %s" % (type(e).__name__, str(e)[:300])}
                    if time.monotonic() > deadline:
                        res = None             # cut short by the budget: left for the next call
                        break
            if res is not None:
                save(out, res)
                with lock:
                    stats["done"] += 1
                    stats["errors"] += 1 if res.get("error") else 0
    finally:
        if c:
            c.close()


def cmd_run(a):
    for s in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(s, on_signal)
    out = pathlib.Path(a.out).resolve()
    (out / "results").mkdir(parents=True, exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    clone = pathlib.Path(a.clone).resolve()
    if not (clone / "flow" / "index.html").exists():
        sys.exit("no flow/index.html in %s" % clone)
    if not os.path.exists(CHROME):
        sys.exit("Chrome is not installed at " + CHROME)
    jobs = select_jobs(a)
    left, marker = pending(a, out, jobs)
    t0 = time.monotonic()
    if left:
        how = serve(a.serve, clone, a.port)
        root = tempfile.mkdtemp(prefix="va-run-")
        q = queue.Queue()
        for j in left:
            q.put(j)
        stats, lock = {"done": 0, "errors": 0}, threading.Lock()
        deadline = t0 + a.budget
        ths = []
        for _ in range(max(1, min(a.workers, len(left)))):
            t = threading.Thread(target=worker, args=(q, a, "http://localhost:%d/" % a.port, out, root, deadline, stats, lock),
                                 daemon=True)
            t.start()
            ths.append(t)
            time.sleep(0.15)
        for t in ths:
            t.join(max(1.0, deadline + 30 - time.monotonic()))
        kill_all()
        shutil.rmtree(root, ignore_errors=True)
        print("served by %s on port %d; %d jobs done (%d ended in an error) in %.0f s"
              % (how, a.port, stats["done"], stats["errors"], time.monotonic() - t0))
    left, marker = pending(a, out, jobs)
    print("%d of the %d jobs in this selection still to run" % (len(left), len(jobs)))
    if left:
        return 3
    if marker is not None and marker.exists():
        marker.unlink()
    write_reports(out, a)
    print("reports written to %s" % out)
    return 0

# ------------------------------------------------------------ reports
SEV = {"high": 3, "medium": 2, "low": 1}
CART_STATES = ("cart-1", "cart-5", "ar-cart")
PDP_STATES = ("pdp-attar", "pdp-edp", "pdp-bakhoor", "pdp-gift", "pdp-long", "ar-pdp")


def load_results(out):
    res = []
    for f in sorted((out / "results").glob("*.json")):
        try:
            res.append(json.loads(f.read_text()))
        except ValueError:
            pass
    return res


def derive(r, a):
    """Every issue of one result, with this report's thresholds applied to
    the raw text sizes, fields, tap targets and bar shares."""
    out = list(r.get("issues") or [])
    touch = GROUP.get(r["vp"]) != "desktops"
    lim = a.min_font if touch else a.min_font_desktop
    for t in r.get("texts") or []:
        if t["fs"] < lim - 0.01:
            out.append({"type": "small-text", "sev": "high" if touch else "medium", "sig": t["sig"], "text": t["text"],
                        "detail": "%gpx, %d run(s)%s" % (t["fs"], t["n"], " (inline style on %s)" % t["inline"] if t.get("inline") else "")})
    if touch:
        for f in r.get("fields") or []:
            if f["fs"] < 16:
                out.append({"type": "field-under-16", "sev": "medium", "sig": f["sig"], "text": "", "detail": "%gpx" % f["fs"]})
        for t in r.get("taps") or []:
            m = min(t["w"], t["h"])
            typ, sev = (("tap-inline-link", "low") if t.get("inline") else
                        ("tap-under-24", "high") if m < 24 else ("tap-under-44", "medium"))
            out.append({"type": typ, "sev": sev, "sig": t["sig"], "text": t.get("text", ""),
                        "detail": "%dx%d, %d on the page" % (t["w"], t["h"], t["n"])})
    b = r.get("bars") or {}
    if b.get("share", 0) > a.max_bar_share:
        out.append({"type": "bar-share", "sev": "medium", "sig": " + ".join(x["sig"] for x in b.get("items", [])), "text": "",
                    "detail": "%d%% of the screen once scrolled" % round(b["share"] * 100)})
    rest = r.get("rest") or {}
    if r["state"] != "coll-filters" and r["state"] != "pdp-added" and rest.get("share", 0) > 0.5:
        out.append({"type": "first-screen-furniture", "sev": "medium", "sig": "header and bars", "text": "",
                    "detail": "%d%% of the first screen (header ends at %s)" % (round(rest["share"] * 100), rest.get("header"))})
    if r.get("error"):
        out.append({"type": "job-error", "sev": "high", "sig": "", "text": "", "detail": r["error"]})
    return out


def compact(vps):
    vps = set(vps)
    parts = []
    for g in GROUPS:
        mine = [v for v in SETS[g] if v in vps]
        if mine:
            parts.append(("all " + g) if len(mine) == len(SETS[g]) else " ".join(mine))
    return ", ".join(parts)


def coverage(vps):
    vps = set(vps)
    return ", ".join("%s %d/%d" % (g, sum(v in vps for v in SETS[g]), len(SETS[g]))
                     for g in GROUPS if any(v in vps for v in SETS[g]))


def write_reports(out, a):
    rs = load_results(out)
    cells = {(r["state"], r["vp"]): (r, derive(r, a)) for r in rs}
    types = {}
    for (st, vp), (r, iss_) in cells.items():
        for i in iss_:
            t = types.setdefault(i["type"], {})
            e = t.setdefault(i["sig"], {"sig": i["sig"], "sev": i["sev"], "cells": [], "example": None})
            if SEV[i["sev"]] > SEV[e["sev"]]:
                e["sev"] = i["sev"]
            if (st, vp) not in e["cells"]:
                e["cells"].append((st, vp))
            if e["example"] is None:
                e["example"] = {"state": st, "vp": vp, "text": i.get("text", ""), "detail": i.get("detail", ""), "shot": r.get("shot")}
    order = sorted(types, key=lambda t: (-max(SEV[e["sev"]] for e in types[t].values()),
                                         -len({c for e in types[t].values() for c in e["cells"]}), t))
    L = ["Viewport audit: %d results (%d ended in an error) in %s" % (len(rs), sum(1 for r in rs if r.get("error")), out),
         "Thresholds: text under %gpx on phones and tablets and under %gpx on desktops; form fields under 16px, "
         "tap targets under 44px on touch screens; bars over %d%% of the screen once scrolled."
         % (a.min_font, a.min_font_desktop, round(a.max_bar_share * 100)), ""]
    # per viewport group
    L.append("By viewport group: cells with a high issue / cells run, then the cells each type touches")
    group_json = {}
    for g in GROUPS:
        mine = [(k, v) for k, v in cells.items() if GROUP.get(k[1]) == g]
        if not mine:
            continue
        hi = sum(1 for _, (_, ii) in mine if any(i["sev"] == "high" for i in ii))
        by = {}
        for k, (_, ii) in mine:
            for t in {i["type"] for i in ii}:
                by[t] = by.get(t, 0) + 1
        group_json[g] = {"cells": len(mine), "high_cells": hi, "types": by}
        L.append("  %-9s %3d/%-3d  %s" % (g, hi, len(mine), ", ".join("%s %d" % kv for kv in sorted(by.items(), key=lambda kv: -kv[1])) or "nothing"))
    L.append("")
    touch_cells = [(k, ii) for k, (_, ii) in cells.items() if GROUP.get(k[1]) != "desktops"]
    crit = [("text under the threshold on phones and tablets", [k for k, ii in touch_cells if any(i["type"] == "small-text" for i in ii)]),
            ("sideways scrolling", [k for k, (_, ii) in cells.items() if any(i["type"] == "overflow" for i in ii)]),
            ("a primary action covered", [k for k, (_, ii) in cells.items() if any(i["type"] == "action-covered" for i in ii)]),
            ("the bag's Checkout out of reach", [k for k, (_, ii) in cells.items() if any(i["type"] == "checkout-unreachable" for i in ii)]),
            ("Add to bag out of reach", [k for k, (_, ii) in cells.items() if any(i["type"] in ("add-unreachable", "added-checkout-missing") for i in ii)]),
            ("script errors", [k for k, (_, ii) in cells.items() if any(i["type"] == "js-error" for i in ii)])]
    L.append("Stop criteria (cells)")
    for name, ks in crit:
        L.append("  %-48s %d%s" % (name, len(ks), ("  e.g. " + ", ".join("%s@%s" % k for k in sorted(ks)[:4])) if ks else ""))
    L.append("")
    js_types = {}
    for t in order:
        els = sorted(types[t].values(), key=lambda e: (-SEV[e["sev"]], -len(e["cells"]), e["sig"]))
        ncell = len({c for e in els for c in e["cells"]})
        L.append("== %s: %d element(s), %d cell(s)" % (t, len(els), ncell))
        rows = []
        for e in els[:a.top]:
            vps = [c[1] for c in e["cells"]]
            ex = e["example"]
            rows.append({"sig": e["sig"], "sev": e["sev"], "cells": len(e["cells"]), "pages": sorted({c[0] for c in e["cells"]}),
                         "viewports": compact(vps), "coverage": coverage(vps), "example": ex})
            L.append("  [%s] %s  (%d cells)" % (e["sev"], e["sig"] or "-", len(e["cells"])))
            L.append("      pages: %s" % ", ".join(sorted({c[0] for c in e["cells"]})))
            L.append("      viewports: %s | %s" % (compact(vps), coverage(vps)))
            L.append("      e.g. %s@%s: %s%s  %s" % (ex["state"], ex["vp"], ex["detail"], (' "%s"' % ex["text"][:40]) if ex.get("text") else "", ex.get("shot") or ""))
        if len(els) > a.top:
            L.append("  ... and %d more" % (len(els) - a.top))
        js_types[t] = rows
        L.append("")
    (out / "report.txt").write_text("\n".join(L) + "\n")
    (out / "report.json").write_text(json.dumps({"results": len(rs), "groups": group_json, "types": js_types,
                                                 "criteria": {n: len(k) for n, k in crit},
                                                 "thresholds": {"min_font": a.min_font, "min_font_desktop": a.min_font_desktop,
                                                                "max_bar_share": a.max_bar_share}}, indent=1))
    write_matrix(out, cells)
    write_checkout(out, cells)


def write_matrix(out, cells):
    vps = [v for v, _ in VIEWPORTS if any(k[1] == v for k in cells)]
    sts = [s for s in STATES if any(k[0] == s for k in cells)]
    L = ["High/medium issue counts per page state (rows) and viewport (columns); . = not run", ""]
    L.append("%-13s " % "" + " ".join("%-9s" % v for v in vps))
    worst = []
    for s in sts:
        row = []
        for v in vps:
            c = cells.get((s, v))
            if not c:
                row.append("%-9s" % ".")
                continue
            h = sum(1 for i in c[1] if i["sev"] == "high")
            m = sum(1 for i in c[1] if i["sev"] == "medium")
            row.append("%-9s" % ("%d/%d" % (h, m)))
            worst.append((h, m, s, v, c[0].get("shot")))
        L.append("%-13s " % s + " ".join(row))
    L += ["", "Worst cells"]
    for h, m, s, v, sh in sorted(worst, key=lambda x: (-x[0], -x[1]))[:25]:
        if h or m:
            L.append("  %d high, %d medium  %s@%s  %s" % (h, m, s, v, sh or ""))
    (out / "matrix.txt").write_text("\n".join(L) + "\n")


def write_checkout(out, cells):
    def cell(s, v):
        c = cells.get((s, v))
        if not c:
            return "."
        r, ii = c
        ac = r.get("acts") or {}
        if "bagbar" in ac:
            x, b = ac.get("checkout", {}), ac.get("bagbar", {})
            if not x.get("found"):
                return "no checkout"
            reach = not any(i["type"] == "checkout-unreachable" for i in ii)
            return "%s %s bar:%s %s" % (x.get("top"), "first" if x.get("inFirst") else "below",
                                        "on" if b.get("found") and b.get("onScreen") else "off", "ok" if reach else "OUT")
        x, st = ac.get("add", {}), ac.get("sticky", {})
        if not x.get("found"):
            return "no add"
        reach = not any(i["type"] == "add-unreachable" for i in ii)
        return "%s-%s %s sticky:%s %s" % (x.get("top"), x.get("bottom"), "first" if x.get("inFirst") else "below",
                                          "on" if st.get("found") and st.get("onScreen") else "off", "ok" if reach else "OUT")

    vps = [v for v, _ in VIEWPORTS if any(k[1] == v for k in cells)]
    L = ["The bag's Checkout: its top edge at rest, on the first screen or below it, the checkout bar, and",
         "whether a Checkout is in reach (ok) or not (OUT).", ""]
    L.append("%-10s " % "" + "".join("%-30s" % s for s in CART_STATES))
    for v in vps:
        L.append("%-10s " % v + "".join("%-30s" % cell(s, v) for s in CART_STATES))
    L += ["", "Product page Add to bag: its top and bottom at rest, first screen or below, the sticky bar, in reach."]
    L.append("%-10s " % "" + "".join("%-30s" % s for s in PDP_STATES))
    for v in vps:
        L.append("%-10s " % v + "".join("%-30s" % cell(s, v) for s in PDP_STATES))
    (out / "checkout.txt").write_text("\n".join(L) + "\n")


def cmd_report(a):
    out = pathlib.Path(a.out).resolve()
    if not (out / "results").is_dir():
        sys.exit("no results in %s" % out)
    write_reports(out, a)
    print((out / "report.txt").read_text().split("\n== ")[0])
    return 0


def cmd_list(_a):
    print("Viewports (%d); phones and landscape at DSF 3, tablets at 2, both mobile with touch; desktops at 1" % len(VIEWPORTS))
    for g in GROUPS:
        print("  %-9s %s" % (g, " ".join(SETS[g])))
    print("  sets: phones, landscape, tablets, desktops, touch, all")
    print("\nPage states (%d)" % len(STATES))
    for s, st in STATES.items():
        extra = []
        if st.get("do"):
            extra.append({"filters": "opens the filter drawer", "add": "presses Add to bag",
                          "quiz": "answers every question", "ar": "switches to Arabic"}[st["do"]])
        if "cart" in st:
            extra.append("a bag of %d product(s)%s" % (len(st["cart"]), ", and the free gift's line" if st["cart"] is FIVE else ""))
        print("  %-12s %-40s %s" % (s, st["path"], "; ".join(extra)))
    print("  aliases: " + ", ".join("%s (%d)" % (k, len(v)) for k, v in ALIASES.items()))
    n_en = sum(1 for s in STATES if not s.startswith("ar-")) * len(VIEWPORTS)
    n_ar = sum(1 for s in STATES if s.startswith("ar-")) * len(AR_DEFAULT.split(","))
    print("\nThe whole matrix: %d jobs (%d English, %d Arabic on %s)" % (n_en + n_ar, n_en, n_ar, AR_DEFAULT))
    return 0


def main():
    ap = argparse.ArgumentParser(description="The storefront at 28 viewports and 29 page states, in headless Chrome.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the viewports and the page states")
    r = sub.add_parser("run", help="run the jobs that have no result yet, within the budget")
    r.add_argument("--clone", required=True, help="the checkout to serve (its flow/ is the shop)")
    r.add_argument("--port", type=int, required=True)
    r.add_argument("--out", required=True)
    r.add_argument("--viewports", default="all")
    r.add_argument("--pages", default="all")
    r.add_argument("--ar-viewports", default=AR_DEFAULT)
    r.add_argument("--workers", type=int, default=7)
    r.add_argument("--budget", type=float, default=72, help="seconds to keep taking new jobs")
    r.add_argument("--full", action="store_true", help="also a full-page screenshot")
    r.add_argument("--full-screens", type=int, default=6)
    r.add_argument("--shot-scale", type=float, default=1)
    r.add_argument("--max-crop", type=float, default=0.3)
    r.add_argument("--serve", choices=("auto", "storefront", "http", "none"), default="auto")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--redo", action="store_true")
    g.add_argument("--redo-errors", action="store_true")
    for p in (r, sub.add_parser("report", help="rebuild the reports from the saved results")):
        if p is not r:
            p.add_argument("--out", required=True)
            p.add_argument("--top", type=int, default=30)
        else:
            p.add_argument("--top", type=int, default=30)
        p.add_argument("--min-font", type=float, default=12)
        p.add_argument("--min-font-desktop", type=float, default=11)
        p.add_argument("--max-bar-share", type=float, default=0.3)
    a = ap.parse_args()
    sys.exit({"list": cmd_list, "run": cmd_run, "report": cmd_report}[a.cmd](a))


if __name__ == "__main__":
    main()
