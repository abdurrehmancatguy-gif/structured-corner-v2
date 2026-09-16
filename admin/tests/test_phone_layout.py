"""The storefront's layout on phones and other touch screens, measured in
headless Chrome: what the viewport audit (admin/devtools/viewport_audit.py)
found and what was fixed, each held to its fix.

    ADMIN_PHONE_LAYOUT_PORT=4792 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_phone_layout.py'

The pages come from a temporary clone (Box, --no-push). Phones are emulated
as mobiles with touch at a device scale of 3, tablets at 2, a desktop at 1
with a mouse; an iPhone's notch through Chrome's emulated safe-area insets.
Sizes are read from computed styles and boxes, never from screenshots.
"""
import json
import os
import time
import unittest

from box import Box
import cdp_pipe

PORT = int(os.environ.get("ADMIN_PHONE_LAYOUT_PORT", "4792"))
J = json.dumps
# four products and, over AED 300, the free gift's line
FIVE = [{"id": "royal-amber", "qty": 2}, {"id": "vibe", "qty": 1}, {"id": "bakhoor-1", "qty": 1},
        {"id": "discovery-trio", "qty": 1}]


@unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
class PhoneLayout(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def setUp(self):
        self.c = cdp_pipe.Chrome()

    def tearDown(self):
        self.c.close()

    # ---- helpers -------------------------------------------------------------
    def view(self, w, h, kind="phone"):
        touch = kind != "desktop"
        self.c.call("Emulation.setDeviceMetricsOverride", {
            "width": w, "height": h, "deviceScaleFactor": {"phone": 3, "tablet": 2, "desktop": 1}[kind],
            "mobile": touch, "screenWidth": w, "screenHeight": h,
            "screenOrientation": {"type": "portraitPrimary", "angle": 0} if h >= w else {"type": "landscapePrimary", "angle": 90}})
        self.c.call("Emulation.setTouchEmulationEnabled", {"enabled": touch, "maxTouchPoints": 5 if touch else 1})

    def insets(self, left=0, right=0, bottom=0):
        """An iPhone's safe area: the notch at the sides in landscape."""
        self.c.call("Emulation.setSafeAreaInsetsOverride", {"insets": {
            "left": left, "leftMax": left, "right": right, "rightMax": right,
            "bottom": bottom, "bottomMax": bottom, "top": 0, "topMax": 0}})

    def open(self, path, bag=None):
        url = "http://localhost:%d/%s" % (PORT, path)
        ready = "document.readyState === 'complete' && !!window.BGS_COPY"
        self.c.go(url)
        self.c.wait(ready, 30)
        if bag is not None:
            self.c.js("localStorage.setItem('bgs_cart', %s)" % J(J(bag)))
            self.c.go(url)
            self.c.wait(ready, 30)
        time.sleep(0.3)

    def js(self, expr):
        return self.c.js(expr)

    def pads(self, sel):
        return self.js("(() => { const s = getComputedStyle(document.querySelector(%s)); "
                       "return [parseFloat(s.paddingLeft), parseFloat(s.paddingRight)]; })()" % J(sel))

    def rect(self, sel, idx=0):
        return self.js("(() => { const e = document.querySelectorAll(%s)[%d]; if (!e) return null; const r = e.getBoundingClientRect(); "
                       "return {left: r.left, top: r.top, right: r.right, bottom: r.bottom, width: r.width, height: r.height}; })()"
                       % (J(sel), idx))

    def press(self, sel, idx=0, scroll=True):
        """A click through Chrome's input pipeline at the middle of an element."""
        if scroll:
            self.js("document.querySelectorAll(%s)[%d].scrollIntoView({block: 'center'})" % (J(sel), idx))
            time.sleep(0.2)
        r = self.rect(sel, idx)
        self.assertTrue(r, "nothing at %s" % sel)
        x, y = r["left"] + r["width"] / 2, r["top"] + r["height"] / 2
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.c.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})

    def no_page_errors(self):
        self.assertEqual(self.c.errors(), [], "the page threw or logged an error")

    # ---- the notch -------------------------------------------------------------
    ROWS = (".strip .wrap", ".mast .wrap", ".catnav .wrap", "section .wrap", "footer .wrap")

    def test_landscape_rows_keep_clear_of_the_notch(self):
        # iPhone 12 to 14 in landscape: the phone layout, and the product page's buy bar too
        self.view(844, 390)
        self.insets(47, 47, 21)
        self.open("product.html?p=royal-amber", bag=[])
        for sel in self.ROWS + (".stickybuy",):
            self.assertEqual(self.pads(sel), [47, 47], sel)
        # Plus and Pro Max in landscape get the desktop layout
        self.view(932, 430)
        self.insets(59, 59, 21)
        self.open("product.html?p=royal-amber")
        for sel in self.ROWS + (".stickybuy",):
            self.assertEqual(self.pads(sel), [59, 59], sel)
        self.press(".atcrow [data-add]")
        self.c.wait("document.querySelector('.added.on') !== null", 10, what="the added-to-bag card")
        self.assertAlmostEqual(self.rect(".added")["right"], 932 - 59, delta=1, msg="the card stays out of the inset")
        # without a notch every row keeps the padding it had
        self.insets()
        self.open("product.html?p=royal-amber")
        for sel in self.ROWS + (".stickybuy",):
            self.assertEqual(self.pads(sel), [28, 28], sel)
        self.view(844, 390)
        self.open("product.html?p=royal-amber")
        self.assertEqual(self.pads(".stickybuy"), [14, 14])
        self.no_page_errors()

    # ---- type on the big landscape phones ----------------------------------------
    def sizes(self, sels):
        return self.js("(() => { const o = {}; for (const s of %s) { const e = [...document.querySelectorAll(s)]"
                       ".find((x) => x.getBoundingClientRect().width > 0); o[s] = e ? parseFloat(getComputedStyle(e).fontSize) : null; }"
                       " return o; })()" % J(sels))

    def lines(self, sel):
        """How many lines each visible match's text takes."""
        return self.js("""[...document.querySelectorAll(%s)].filter((b) => b.getBoundingClientRect().width > 0).map((b) => {
          const ls = [], rg = document.createRange(); rg.selectNodeContents(b);
          for (const q of rg.getClientRects()) if (q.width >= 1 && !ls.some((t) => Math.abs(t - q.top) < 3)) ls.push(q.top);
          return ls.length; })""" % J(sel))

    BAG_TEXT = {".lmeta": 14, ".line .lrem": 14, ".prog .lb": 14, ".stepper i": 16, ".lname": 16, ".sum .r": 15, ".codnote": 14}
    PDP_TEXT = {".atcrow [data-add]": 15, ".permeta": 14, ".tabs2 button": 14, ".kv div": 14, ".p .btn.sm": 15, ".p .nm": 16}

    def test_the_big_landscape_phones_read_the_phone_sizes(self):
        for w, h in ((915, 412), (932, 430)):
            self.view(w, h)
            self.open("cart.html", bag=FIVE)
            self.assertEqual(self.sizes(list(self.BAG_TEXT)), self.BAG_TEXT, "the bag at %dx%d" % (w, h))
            self.open("product.html?p=royal-amber")
            self.assertEqual(self.sizes(list(self.PDP_TEXT)), self.PDP_TEXT, "the product page at %dx%d" % (w, h))
            # card size chips stack, one line each
            self.open("gift-box.html")
            chips = self.lines(".two .grid.g4 .p .sizes button")
            self.assertTrue(chips and set(chips) == {1}, "gift box chips take %s lines" % chips)
            self.open("collection.html?cat=attars")
            chips = self.lines("[data-grid] .p .sizes button")
            self.assertTrue(chips and set(chips) == {1}, "collection chips take %s lines" % chips)
        # a desktop with a mouse keeps its sizes
        self.view(1440, 900, "desktop")
        self.open("cart.html", bag=FIVE)
        self.assertEqual(self.sizes([".lmeta", ".stepper i", ".sum .r"]), {".lmeta": 12.5, ".stepper i": 13, ".sum .r": 13.5})
        self.no_page_errors()

    # ---- the bag heading in Arabic ---------------------------------------------
    TITLE = """(() => { const h = document.querySelector('h2.pagetitle'), sp = h.querySelector('[data-bagitems]');
      const t = [...h.childNodes].find((n) => n.nodeType === 3 && n.nodeValue.trim());
      const box = (n, a, b) => { const r = document.createRange(); if (a === undefined) r.selectNodeContents(n); else { r.setStart(n, a); r.setEnd(n, b); }
        const q = r.getBoundingClientRect(); return [q.left, q.right]; };
      const sep = sp.firstChild, i = sep && sep.nodeType === 3 ? sep.nodeValue.indexOf(String.fromCharCode(0xB7)) : -1;
      const c = sp.querySelector('bdi');
      return {word: box(t), dot: i >= 0 ? box(sep, i, i + 1) : null, text: c ? c.textContent : null,
              count: c ? [c.getBoundingClientRect().left, c.getBoundingClientRect().right] : null}; })()"""

    def test_the_bag_title_keeps_its_dot_between_the_title_and_the_count(self):
        for w, h, kind in ((320, 568, "phone"), (1440, 900, "desktop")):
            self.view(w, h, kind)
            self.open("cart.html", bag=FIVE)
            en = self.js("window.BGS_COPY.cart.items.many").replace("{n}", "5")
            t = self.js(self.TITLE)
            self.assertEqual(t["text"], en)
            self.assertTrue(t["word"][1] < t["dot"][0] < t["dot"][1] < t["count"][0], "title, dot, count: %s" % t)
            # Arabic: title, dot and count from the right, a space either side of the dot
            self.js("document.querySelector('[data-langtoggle]').click()")
            ar = self.js("window.BGS_AR['{n} items'] || '{n} items'").replace("{n}", "5")
            t = self.js(self.TITLE)
            self.assertEqual(t["text"], ar, "the count in Arabic")
            self.assertGreaterEqual(t["word"][0] - t["dot"][1], 2, "a space between the title and the dot: %s" % t)
            self.assertGreaterEqual(t["dot"][0] - t["count"][1], 2, "a space between the dot and the count: %s" % t)
            # and back
            self.js("document.querySelector('[data-langtoggle]').click()")
            t = self.js(self.TITLE)
            self.assertEqual(t["text"], en, "the count in English again")
            self.assertTrue(t["word"][1] < t["dot"][0] < t["dot"][1] < t["count"][0], "title, dot, count: %s" % t)
        self.no_page_errors()

    # ---- the bag's progress rows ---------------------------------------------------
    PROG = """(() => [...document.querySelectorAll('[data-cartprogress] .lb')].map((lb) => {
      const a = lb.firstElementChild, b = lb.lastElementChild;
      const rects = (e) => { const r = document.createRange(); r.selectNodeContents(e); return [...r.getClientRects()].filter((q) => q.width >= 1); };
      let gap = null;
      for (const x of rects(a)) for (const y of rects(b)) {
        if (Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) < 2) continue;
        const g = Math.max(y.left - x.right, x.left - y.right);
        if (gap === null || g < gap) gap = g;
      }
      const tops = rects(b).map((q) => Math.round(q.top));
      return {label: a.textContent.trim(), status: b.textContent.trim(), gap, statusLines: new Set(tops).size};
    }))()"""

    def test_the_bag_progress_rows_keep_their_label_and_status_apart(self):
        for w, h, ar, bag in ((280, 653, False, FIVE), (280, 653, False, [{"id": "royal-amber", "qty": 1}]),
                              (320, 568, True, FIVE), (390, 844, False, FIVE)):
            self.view(w, h)
            self.open("cart.html", bag=bag)
            if ar:
                self.js("document.querySelector('[data-langtoggle]').click()")
            rows = self.js(self.PROG)
            self.assertEqual(len(rows), 3)
            for r in rows:
                if r["gap"] is not None:      # side by side on a line they share
                    self.assertGreaterEqual(r["gap"], 8, "%dx%d%s: %s" % (w, h, " ar" if ar else "", r))
                self.assertEqual(r["statusLines"], 1, r)
        self.no_page_errors()

    # ---- the phone masthead ------------------------------------------------------
    MAST = """(() => { const acts = [...document.querySelectorAll('.mast .acts .act')].filter((a) => a.getBoundingClientRect().width > 0)
        .map((a) => { const r = a.getBoundingClientRect(); return [r.width, r.height, r.left, r.right]; });
      const logo = document.querySelector('.mast .logo'), img = logo.querySelector('img'), r = logo.getBoundingClientRect(), i = img.getBoundingClientRect();
      return {acts, logo: [r.left, r.right, i.width / i.height, img.naturalWidth / img.naturalHeight],
              wide: document.documentElement.scrollWidth}; })()"""

    def test_the_masthead_icons_are_44px_at_every_phone_width(self):
        for w, h in ((280, 653), (320, 568), (340, 720), (360, 640)):
            self.view(w, h)
            self.open("index.html")
            m = self.js(self.MAST)
            self.assertEqual(len(m["acts"]), 3, "search, wishlist and bag at %d" % w)
            for a in m["acts"]:
                self.assertGreaterEqual(min(a[0], a[1]), 44, "%d: %s" % (w, m["acts"]))
            self.assertLessEqual(m["logo"][1], m["acts"][0][2] + 0.5, "the logo stays clear of the icons at %d" % w)
            self.assertAlmostEqual(m["logo"][2], m["logo"][3], delta=0.1, msg="the logo keeps its shape at %d" % w)
            self.assertLessEqual(m["wide"], w, "no sideways scrolling at %d" % w)
        self.no_page_errors()

    # ---- the product page's buy bar ------------------------------------------------
    STICKY = """(() => { const s = document.querySelector('.stickybuy'), sp = s.querySelector('span');
      const r = document.createRange(); r.selectNodeContents(sp);
      const tops = new Set([...r.getClientRects()].filter((q) => q.width >= 1).map((q) => Math.round(q.top)));
      return {hidden: s.classList.contains('hidden'), height: s.getBoundingClientRect().height, lines: tops.size,
              meta: sp.textContent}; })()"""

    def test_the_buy_bar_keeps_its_details_on_one_line(self):
        for w, h in ((280, 653), (320, 568), (360, 640)):
            self.view(w, h)
            # Majlis OUD, with two sizes and the highest prices, stands in for the Eid
            # Royal Hamper, which is off the shop until it has a photo
            for pid in ("royal-amber", "majlis-oud"):
                self.open("product.html?p=" + pid)
                self.js("scrollTo(0, 1100)")
                self.c.wait("!document.querySelector('.stickybuy').classList.contains('hidden')", 5, what="the buy bar")
                time.sleep(0.3)
                s = self.js(self.STICKY)
                self.assertTrue(s["meta"].startswith("AED "), s)
                self.assertEqual(s["lines"], 1, "%s at %d: %s" % (pid, w, s))
                self.assertLessEqual(s["height"], 64, "%s at %d: %s" % (pid, w, s))
        self.no_page_errors()

    # ---- landscape: the added-to-bag panel and the bag's bar -------------------------
    def test_landscape_panel_and_bag_bar_keep_14px_secondary_text(self):
        for w, h in ((667, 375), (844, 390)):
            self.view(w, h)
            self.open("product.html?p=vibe", bag=[])
            self.press(".atcrow [data-add]")
            self.c.wait("document.querySelector('.added.on') !== null", 10, what="the added-to-bag sheet")
            self.assertEqual(self.sizes([".added-hd", ".added-s span"]), {".added-hd": 14, ".added-s span": 14}, "%dx%d" % (w, h))
        for w, h in ((915, 412), (932, 430)):
            self.view(w, h)
            self.open("cart.html", bag=FIVE)
            self.c.wait("document.querySelector('[data-bagbar]').classList.contains('on')", 5, what="the bag's bar")
            self.assertEqual(self.sizes([".bagbar .bb-t span"]), {".bagbar .bb-t span": 14}, "%dx%d" % (w, h))
        self.no_page_errors()

    # ---- a reader's own text size -------------------------------------------------
    BIG = ("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
           "s.textContent = 'html{-webkit-text-size-adjust:200% !important;text-size-adjust:200% !important}'; "
           "document.head.appendChild(s); });")

    def big_text(self):
        """Text at 200%, as a phone's own text size setting enlarges it; returns
        the script's id for Page.removeScriptToEvaluateOnNewDocument."""
        return self.c.call("Page.addScriptToEvaluateOnNewDocument", {"source": self.BIG})["identifier"]

    SORTROW = """(() => { const d = document.querySelector('.toolbar:has(.sel) > div:has(> .sel)');
      const a = d.querySelector('.count').getBoundingClientRect(), b = d.querySelector('.sel').getBoundingClientRect();
      return {oneLine: b.top < a.bottom && a.top < b.bottom, right: Math.max(a.right, b.right)}; })()"""

    BAGBAR = """(() => { const b = document.querySelector('[data-bagbar]'), t = b.querySelector('.bb-t b'), a = b.querySelector('.btn');
      const r = document.createRange(); r.selectNodeContents(t);
      const q = [...r.getClientRects()].filter((x) => x.width >= 1);
      return {on: b.classList.contains('on'), textRight: Math.max(...q.map((x) => x.right)), lines: new Set(q.map((x) => Math.round(x.top))).size,
              btnLeft: a.getBoundingClientRect().left, spill: t.scrollWidth - t.clientWidth}; })()"""

    def test_the_bag_bar_total_stays_clear_of_checkout_at_200_percent_text(self):
        self.view(390, 844)
        self.open("cart.html", bag=FIVE)
        self.c.wait("document.querySelector('[data-bagbar]').classList.contains('on')", 5, what="the bag's bar")
        s = self.js(self.BAGBAR)
        self.assertEqual(s["lines"], 1, "one line at the usual size: %s" % s)
        sid = self.big_text()
        try:
            self.open("cart.html")
            self.c.wait("document.querySelector('[data-bagbar]').classList.contains('on')", 5, what="the bag's bar")
            self.assertEqual(self.js("getComputedStyle(document.body).fontSize"), "32px", "the text is at 200%")
            s = self.js(self.BAGBAR)
            self.assertLessEqual(s["spill"], 0, "the total stays in its box: %s" % s)
            self.assertLess(s["textRight"], s["btnLeft"], "the total ends before Checkout starts: %s" % s)
        finally:
            self.c.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": sid})
        self.no_page_errors()

    def test_the_collection_fits_a_phone_at_200_percent_text(self):
        self.view(390, 844)
        self.open("collection.html")
        self.assertTrue(self.js(self.SORTROW)["oneLine"], "the count and the sort box share a line at the usual size")
        sid = self.big_text()
        try:
            self.open("collection.html")
            self.assertEqual(self.js("getComputedStyle(document.body).fontSize"), "32px", "the text is at 200%")
            self.assertEqual(self.js("innerWidth"), 390, "the page does not widen past the phone")
            self.assertLessEqual(self.js(self.SORTROW)["right"], 390)
        finally:
            self.c.call("Page.removeScriptToEvaluateOnNewDocument", {"identifier": sid})
        self.no_page_errors()


if __name__ == "__main__":
    unittest.main()
