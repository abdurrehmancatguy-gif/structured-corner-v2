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


if __name__ == "__main__":
    unittest.main()
