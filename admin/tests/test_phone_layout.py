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
        self.press(".atcrow [data-add]", scroll=False)
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


if __name__ == "__main__":
    unittest.main()
