"""The way from Add to bag to checkout, driven in headless Chrome on the
storefront: the panel that opens after every Add, on a phone and on a
desktop, and the checkout bar on the bag page on phones.

    ADMIN_BAG_PATH_PORT=4791 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_bag_path.py'

The pages come from a temporary clone (Box, --no-push). A phone is emulated
as a mobile with touch at a device scale of 3, a desktop at 1. Clicks go
through Chrome's input pipeline, so focus lands where a person's click puts
it; the words are read from BGS_COPY and BGS_AR, so an edit in Pages does not
break the test.
"""
import json
import os
import time
import unittest

from box import Box
import cdp_pipe

PORT = int(os.environ.get("ADMIN_BAG_PATH_PORT", "4791"))
J = json.dumps
# four products and, over AED 300, the free gift's line
FIVE = [{"id": "royal-amber", "qty": 2}, {"id": "vibe", "qty": 1}, {"id": "bakhoor-1", "qty": 1},
        {"id": "discovery-trio", "qty": 1}]
PANEL = """(() => { const e = document.querySelector('.added'); if (!e) return null;
  const r = e.getBoundingClientRect(), t = document.querySelector('.tabbar'), tr = t.getBoundingClientRect();
  const b = [...e.querySelectorAll('.added-b a')];
  return {n: document.querySelectorAll('.added').length, open: !e.hidden && e.classList.contains('on'),
    anchored: e.classList.contains('anchored'), top: r.top, bottom: r.bottom, left: r.left, right: r.right,
    tab: getComputedStyle(t).display === 'none' ? null : tr.top, title: e.querySelector('[data-at]').textContent,
    name: e.querySelector('.added-nm').textContent, qty: e.querySelector('.added-q').textContent,
    price: e.querySelector('.added-pr').textContent, sub: e.querySelector('.added-s span').textContent,
    subAmount: e.querySelector('.added-s b').textContent, close: e.querySelector('.added-x').getAttribute('aria-label'),
    links: b.map((a) => [a.textContent, a.getAttribute('href'), a.classList.contains('solid')]),
    live: document.querySelector('[data-addedlive]').textContent}; })()"""
BAR = """(() => { const b = document.querySelector('[data-bagbar]'), r = b.getBoundingClientRect(), t = document.querySelector('.tabbar');
  return {on: b.classList.contains('on'), hidden: b.getAttribute('aria-hidden'), shown: getComputedStyle(b).display,
    visible: getComputedStyle(b).visibility, top: r.top, bottom: r.bottom,
    tab: getComputedStyle(t).display === 'none' ? null : t.getBoundingClientRect().top,
    total: b.querySelector('[data-bagbartotal]').textContent, summary: document.querySelector('[data-total]').textContent,
    link: [b.querySelector('a').textContent, b.querySelector('a').getAttribute('href')]}; })()"""


@unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
class BagPath(unittest.TestCase):
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
    def view(self, w, h, phone=True):
        self.c.call("Emulation.setDeviceMetricsOverride", {"width": w, "height": h, "deviceScaleFactor": 3 if phone else 1,
                                                           "mobile": phone, "screenWidth": w, "screenHeight": h})
        self.c.call("Emulation.setTouchEmulationEnabled", {"enabled": phone, "maxTouchPoints": 5 if phone else 1})

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

    def point(self, sel, idx=0, scroll=True):
        """The middle of an element in the visual viewport's coordinates,
        which Input events use."""
        if scroll:
            self.js("document.querySelectorAll(%s)[%d].scrollIntoView({block: 'center'})" % (J(sel), idx))
            time.sleep(0.2)
        p = self.js("""(() => { const e = document.querySelectorAll(%s)[%d]; if (!e) return null;
          const r = e.getBoundingClientRect(), v = window.visualViewport, s = v ? v.scale : 1;
          return [(r.left + r.width / 2 - (v ? v.offsetLeft : 0)) * s, (r.top + r.height / 2 - (v ? v.offsetTop : 0)) * s]; })()"""
                    % (J(sel), idx))
        self.assertTrue(p, "nothing at %s" % sel)
        return p

    def press(self, x, y):
        for kind in ("mouseMoved", "mousePressed", "mouseReleased"):
            self.c.call("Input.dispatchMouseEvent", {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})

    def click(self, sel, idx=0, scroll=True):
        self.press(*self.point(sel, idx, scroll))

    def click_blank(self):
        """Somewhere on the page that is no control and none of the bars."""
        p = self.js("""(() => { const v = window.visualViewport, s = v ? v.scale : 1;
          for (let y = 140; y < innerHeight - 60; y += 12) for (let x = 12; x < innerWidth - 12; x += 24) {
            const e = document.elementFromPoint(x, y);
            if (e && !e.closest('a,button,input,label,select,textarea,[data-add],.added,.tabbar,.catnav,.stickybuy,[tabindex]'))
              return [(x - (v ? v.offsetLeft : 0)) * s, (y - (v ? v.offsetTop : 0)) * s];
          } return null; })()""")
        self.assertTrue(p, "no blank spot on the page")
        self.press(*p)

    def panel(self):
        return self.js(PANEL)

    def wait_open(self):
        self.c.wait("(() => { const e = document.querySelector('.added'); return !!e && !e.hidden && e.classList.contains('on'); })()",
                    10, what="the added-to-bag panel")
        time.sleep(0.25)

    def wait_closed(self):
        self.c.wait("(() => { const e = document.querySelector('.added'); return !e || e.hidden; })()", 10, what="the panel to close")

    def copy(self, path):
        return self.js("%s.split('.').reduce((o, k) => o[k], window.BGS_COPY)" % J(path))

    def money(self, n):
        return "AED " + ("{:,.2f}".format(n).rstrip("0").rstrip(".") if n % 1 else "{:,.0f}".format(n))

    def price(self, pid):
        return self.js("window.BGS_CATALOGUE[%s].pn" % J(pid))

    def no_page_errors(self):
        self.assertEqual(self.c.errors(), [], "the page threw or logged an error")

    # ---- the panel on a phone ------------------------------------------------
    def test_a_card_add_on_a_phone_opens_one_panel_on_the_tab_bar(self):
        self.view(390, 844)
        self.open("index.html", bag=[])
        card = ".p [data-add]"
        pid = self.js("document.querySelector(%s).getAttribute('data-add')" % J(card))
        name = self.js("window.BGS_CATALOGUE[%s].name" % J(pid))
        self.click(card)
        self.wait_open()
        p = self.panel()
        self.assertEqual(p["n"], 1)
        self.assertAlmostEqual(p["bottom"], p["tab"], delta=1, msg="the sheet rests on the tab bar")
        self.assertEqual((p["left"], p["right"]), (0, 390))
        self.assertTrue(self.js("document.activeElement === document.querySelector(%s)" % J(card)), "focus stays on the button")
        self.assertEqual(p["title"], self.copy("cart.added.title"))
        self.assertEqual((p["name"], p["qty"], p["price"]), (name, "Qty 1", self.money(self.price(pid))))
        self.assertEqual(p["links"], [[self.copy("cart.added.view_bag"), "cart.html", False],
                                      [self.copy("cart.summary.checkout"), "checkout.html", True]])
        self.assertEqual(p["close"], self.copy("cart.added.close"))
        self.c.wait("document.querySelector('[data-addedlive]').textContent.length > 0", 5, what="the announcement")
        self.assertEqual(self.panel()["live"], "%s: %s, Qty 1. Subtotal %s, 1 item." % (p["title"], name, self.money(self.price(pid))))

        # a second press refreshes the one panel
        self.click(card, scroll=False)
        time.sleep(0.4)
        p = self.panel()
        self.assertEqual((p["n"], p["open"], p["qty"], p["sub"]), (1, True, "Qty 2", "Subtotal · 2 items"))
        self.assertEqual((p["price"], p["subAmount"]), (self.money(2 * self.price(pid)),) * 2)
        self.assertEqual(json.loads(self.js("localStorage.getItem('bgs_cart')")), [{"id": pid, "qty": 2}])

        # Escape closes it and leaves focus on the button; a tap elsewhere closes it too
        self.c.key("Escape")
        self.wait_closed()
        self.assertTrue(self.js("document.activeElement === document.querySelector(%s)" % J(card)))
        self.click(card, 1)
        self.wait_open()
        self.assertEqual(self.panel()["n"], 1)
        self.click_blank()
        self.wait_closed()
        self.assertTrue(self.js("location.pathname.endsWith('/index.html')"), "a tap on the page only closes it")

        # its Checkout goes to checkout, the bag as it was
        self.click(card, 2)
        self.wait_open()
        self.click(".added-b a.solid", scroll=False)
        self.c.wait("location.pathname.endsWith('/checkout.html') && document.readyState === 'complete'", 15)
        self.assertEqual(len(json.loads(self.js("localStorage.getItem('bgs_cart')"))), 3)
        self.no_page_errors()

    def test_a_product_page_add_on_a_phone_counts_what_the_bag_holds(self):
        self.view(390, 844)
        self.open("product.html?p=royal-amber", bag=[])
        self.click(".atcrow [data-add]")
        self.wait_open()
        p = self.panel()
        self.assertEqual((p["n"], p["name"], p["qty"], p["price"]), (1, "Royal Amber", "Qty 1", self.money(self.price("royal-amber"))))
        self.assertAlmostEqual(p["bottom"], p["tab"], delta=1)
        # the stepper's quantity goes in; the panel says what the bag now holds
        self.click_blank()
        self.wait_closed()
        self.click("[data-stepper] [data-step='1']")
        self.click("[data-stepper] [data-step='1']", scroll=False)
        self.click(".atcrow [data-add]")
        self.wait_open()
        self.assertEqual(self.panel()["qty"], "Qty 4")
        self.assertEqual(self.js("localStorage.getItem('bgs_cart')"), '[{"id":"royal-amber","qty":4}]')
        self.no_page_errors()

    def test_a_gift_box_pick_opens_no_panel(self):
        self.view(390, 844)
        self.open("gift-box.html", bag=[])
        self.click(".two .grid.g4 .p [data-add]")
        time.sleep(0.6)
        self.assertEqual(self.js("document.querySelectorAll('[data-unpick]').length"), 1, "the card fills a slot")
        self.assertIsNone(self.panel())
        self.assertEqual(self.js("localStorage.getItem('bgs_cart')"), "[]")
        self.no_page_errors()

    def test_in_arabic_the_panel_speaks_arabic(self):
        self.view(390, 844)
        self.open("index.html", bag=[])
        self.js("document.querySelector('[data-langtoggle]').click()")
        self.assertEqual(self.js("document.documentElement.dir"), "rtl")
        self.click(".p [data-add]")
        self.wait_open()
        p = self.panel()
        ar = lambda en: self.js("window.BGS_AR[%s]" % J(en))
        self.assertEqual(p["title"], ar("Added to your bag"))
        self.assertEqual([l[0] for l in p["links"]], [ar("View bag"), ar("Checkout")])
        self.assertEqual((p["close"], p["qty"]), (ar("Close"), ar("Qty {n}").replace("{n}", "1")))
        self.assertAlmostEqual(p["bottom"], p["tab"], delta=1)
        self.no_page_errors()

    # ---- the panel on a desktop ----------------------------------------------
    def test_on_a_desktop_the_panel_hangs_under_the_bag(self):
        self.view(1440, 900, phone=False)
        self.open("product.html?p=royal-amber", bag=[])
        self.click(".atcrow [data-add]", scroll=False)
        self.wait_open()
        p = self.panel()
        bag = self.js("""(() => { const a = document.querySelector('.mast a.act[href="cart.html"]'), r = a.getBoundingClientRect(),
          i = a.querySelector('svg').getBoundingClientRect(); return [r.bottom, r.right, i.left + i.width / 2]; })()""")
        self.assertTrue(p["anchored"])
        self.assertAlmostEqual(p["top"], bag[0] + 12, delta=1)
        self.assertAlmostEqual(p["right"], bag[1], delta=1)
        caret = self.js("parseFloat(getComputedStyle(document.querySelector('.added')).getPropertyValue('--caret'))")
        self.assertAlmostEqual(p["right"] - caret - 6, bag[2], delta=2, msg="the caret points at the bag icon")
        self.assertEqual([l[1] for l in p["links"]], ["cart.html", "checkout.html"])
        self.assertTrue(self.js("document.activeElement.matches('.atcrow [data-add]')"))
        # Tab from the button goes into the panel and Shift+Tab comes back
        self.c.key("Tab")
        self.assertTrue(self.js("document.activeElement === document.querySelector('.added-b a')"))
        self.c.key("Tab", ["shift"])
        self.assertTrue(self.js("document.activeElement.matches('.atcrow [data-add]')"))
        self.c.key("Escape")
        self.wait_closed()

        # a card further down: the masthead has scrolled away, so under the category bar
        self.click(".p [data-add]")
        self.wait_open()
        self.click(".p [data-add]", scroll=False)
        time.sleep(0.4)
        p = self.panel()
        nav = self.js("document.querySelector('.catnav').getBoundingClientRect().bottom")
        self.assertEqual((p["n"], p["anchored"]), (1, False))
        self.assertAlmostEqual(p["top"], max(0, nav) + 12, delta=1)
        self.assertEqual(p["qty"], "Qty 2")
        self.no_page_errors()

    # ---- the checkout bar on the bag page --------------------------------------
    def bar_hands_off(self, w, h):
        self.view(w, h)
        self.open("cart.html", bag=FIVE)
        self.c.wait("document.querySelector('[data-bagbar]').classList.contains('on')", 5, what="the bar on load")
        s = self.js(BAR)
        self.assertEqual((s["hidden"], s["total"]), ("false", s["summary"]))
        self.assertEqual(s["link"], [self.copy("cart.summary.checkout"), "checkout.html"])
        self.assertAlmostEqual(s["bottom"], s["tab"], delta=1, msg="the bar rests on the tab bar")
        self.js("document.querySelector('[data-checkout]').scrollIntoView({block: 'center'})")
        self.c.wait("!document.querySelector('[data-bagbar]').classList.contains('on')", 5, what="the bar to step aside")
        self.c.wait("getComputedStyle(document.querySelector('[data-bagbar]')).visibility === 'hidden'", 5)
        self.js("scrollTo(0, 0)")
        self.c.wait("document.querySelector('[data-bagbar]').classList.contains('on')", 5, what="the bar back")
        before = self.js(BAR)["total"]
        self.click("[data-line] [data-step='1']")
        self.c.wait("document.querySelector('[data-bagbartotal]').textContent !== %s" % J(before), 5, what="the total to follow")
        s = self.js(BAR)
        self.assertEqual(s["total"], s["summary"])
        while self.js("document.querySelectorAll('[data-remove]').length"):
            self.click("[data-remove]")
            time.sleep(0.3)
        self.c.wait("!document.querySelector('[data-cartempty]').hidden", 5)
        self.assertFalse(self.js(BAR)["on"])
        self.no_page_errors()

    def test_the_bag_bar_hands_off_to_the_summary_on_a_portrait_phone(self):
        self.bar_hands_off(390, 844)

    def test_the_bag_bar_hands_off_to_the_summary_on_a_landscape_phone(self):
        self.bar_hands_off(844, 390)

    def test_a_desktop_bag_has_no_bar(self):
        self.view(1440, 900, phone=False)
        self.open("cart.html", bag=FIVE)
        s = self.js(BAR)
        self.assertEqual((s["shown"], s["on"]), ("none", False))
        self.assertTrue(self.js("(() => { const r = document.querySelector('[data-checkout]').getBoundingClientRect(); "
                                "return r.top >= 0 && r.bottom <= innerHeight; })()"), "the summary's Checkout is on screen")
        self.no_page_errors()


if __name__ == "__main__":
    unittest.main()
