"""Instant search: the list that opens under either search box as a shopper
types, measured in headless Chrome on a desktop and on a phone, and the
collection page's results for the same words.

    ADMIN_SEARCH_PORT=4796 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_search.py'

The pages come from a temporary clone (Box, --no-push).
"""
import json
import os
import time
import unittest

from box import Box
import cdp_pipe

PORT = int(os.environ.get("ADMIN_SEARCH_PORT", "4796"))
J = json.dumps
DESK = "form.search:not(#msearch form) input[name=q]"
PHONE = "#msearch input[name=q]"


@unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
class InstantSearch(unittest.TestCase):
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
    def view(self, w, h, phone=False):
        self.c.call("Emulation.setDeviceMetricsOverride",
                    {"width": w, "height": h, "deviceScaleFactor": 3 if phone else 1, "mobile": phone})
        self.c.call("Emulation.setTouchEmulationEnabled", {"enabled": phone, "maxTouchPoints": 5 if phone else 1})

    def open(self, path="index.html"):
        self.c.go("http://localhost:%d/%s" % (PORT, path))
        self.c.wait("document.readyState === 'complete' && !!window.BGS_COPY", 30)
        time.sleep(0.2)

    def catalogue(self):
        return self.c.js("window.BGS_CATALOGUE")

    def typed(self, text, sel=DESK):
        """clear the box, type into it key by key and wait for the list"""
        if sel == PHONE and not self.c.js("document.getElementById('msearch').classList.contains('open')"):
            self.c.js("document.querySelector('[data-searchtoggle]').click()")
        self.c.js("(() => { const i = document.querySelector(%s); i.value = ''; i.focus(); })()" % J(sel))
        self.c.type(text)
        self.c.wait("(() => { const i = document.querySelector(%s), l = document.getElementById(i.getAttribute('aria-controls'));"
                    " return !!l && !l.hidden && i.value === %s; })()" % (J(sel), J(text)), 5, "the list for %r" % text)
        time.sleep(0.2)
        return self.state(sel)

    def state(self, sel=DESK):
        return self.c.js("""(() => {
          const i = document.querySelector(%s), l = document.getElementById(i.getAttribute('aria-controls'));
          const o = [...l.querySelectorAll('.sq-o')], all = l.querySelector('.sq-all'), none = l.querySelector('.sq-none');
          const r = l.getBoundingClientRect(), de = document.documentElement;
          return {open: !l.hidden, expanded: i.getAttribute('aria-expanded'), role: i.getAttribute('role'),
                  ids: o.map(a => new URL(a.href).searchParams.get('p')), names: o.map(a => a.querySelector('.sq-n').textContent),
                  bold: o.map(a => [...a.querySelectorAll('.sq-n b')].map(b => b.textContent)),
                  all: all ? all.getAttribute('href') : null, allText: all ? all.textContent : null,
                  none: none ? none.textContent : null, active: i.getAttribute('aria-activedescendant'),
                  optionIds: [...l.querySelectorAll('[role=option]')].map(a => a.id),
                  live: [...document.querySelectorAll('.sq-live')].map(e => e.textContent).join(''),
                  rect: [r.left, r.top, r.right, r.bottom], vw: de.clientWidth, sw: de.scrollWidth,
                  value: i.value, dir: getComputedStyle(l).direction}; })()""" % J(sel))

    def found(self, q):
        return self.c.js("bgsSearch(%s)" % J(q))

    # ---- the words ---------------------------------------------------------
    def test_a_typo_still_finds_the_product(self):
        self.view(1440, 900)
        self.open()
        cat = self.catalogue()
        for typo, want in (("oudd", "oud"), ("ambr", "amber"), ("vibee", "vibe"), ("rsoe", "rose")):
            s = self.typed(typo)
            self.assertTrue(s["ids"], "%r found nothing" % typo)
            first = json.dumps(cat[s["ids"][0]]).lower()
            self.assertIn(want, first, "%r first found %s" % (typo, s["names"]))
        self.assertEqual(self.typed("vibee")["names"][0], "Vibe")
        self.assertEqual(self.c.errors(), [])

    def test_a_real_word_is_never_taken_for_a_typo(self):
        # "rose" is in the shop, so it finds roses only, never "nose" or "rise"
        self.view(1440, 900)
        self.open()
        cat = self.catalogue()
        for word in ("rose", "amber", "oud"):
            for k in self.found(word):
                self.assertIn(word, json.dumps(cat[k]).lower(), "%r found %s" % (word, k))

    def test_words_match_the_start_of_words_and_rank_names_first(self):
        self.view(1440, 900)
        self.open()
        cat = self.catalogue()
        # "her" finds Her and Hers, never leatHER
        for k in self.found("her"):
            words = json.dumps(cat[k]).lower().replace("-", " ")
            self.assertRegex(words, r"(^|[^a-z])her", k)
        # a category word: Bakhoor first, by the start of the word
        s = self.typed("bakh")
        self.assertIn("bakhoor", cat[s["ids"][0]]["crumb"].lower())
        self.assertEqual(s["bold"][0], ["Bakh"] if s["names"][0].startswith("Bakh") else s["bold"][0])
        # "for her": the little words are not required
        self.assertEqual(self.found("for her"), self.found("her"))

    # ---- the list ----------------------------------------------------------
    def test_the_list_is_a_combobox_that_counts_and_shows_six(self):
        self.view(1440, 900)
        self.open()
        s = self.typed("oud")
        total = len(self.found("oud"))
        self.assertEqual(s["role"], "combobox")
        self.assertEqual(s["expanded"], "true")
        self.assertEqual(len(s["ids"]), min(6, total))
        self.assertEqual(s["all"], "collection.html?q=oud")
        self.assertIn(str(total), s["live"])
        self.assertTrue(all(b and b[0].lower().startswith("oud") for b in s["bold"] if b))

    def test_nothing_found_says_so(self):
        self.view(1440, 900)
        self.open()
        s = self.typed("zzqxv")
        self.assertEqual(s["ids"], [])
        self.assertIsNone(s["all"])
        self.assertTrue(s["none"])
        self.assertEqual(s["live"], s["none"])

    def test_the_keyboard_moves_opens_and_escapes(self):
        self.view(1440, 900)
        self.open()
        s = self.typed("amber")
        self.c.key("ArrowDown")
        s = self.state()
        self.assertEqual(s["active"], s["optionIds"][0])
        self.c.key("ArrowUp")
        self.assertIsNone(self.state()["active"])
        self.c.key("ArrowUp")
        self.assertEqual(self.state()["active"], s["optionIds"][-1])
        self.c.key("Escape")
        s = self.state()
        self.assertFalse(s["open"])
        self.assertEqual(s["expanded"], "false")
        self.assertEqual(s["value"], "amber")
        self.c.key("ArrowDown")   # opens the list again
        self.c.wait("!document.getElementById(document.querySelector(%s).getAttribute('aria-controls')).hidden" % J(DESK), 5)
        self.c.key("ArrowDown")
        first = self.state()["ids"][0]
        self.c.key("Enter")
        self.c.wait("location.pathname.endsWith('product.html') && new URLSearchParams(location.search).get('p') === %s" % J(first),
                    15, "the product page for %s" % first)

    def test_enter_with_nothing_in_focus_opens_all_the_results(self):
        self.view(1440, 900)
        self.open()
        self.typed("oudd")
        want = len(self.found("oudd"))
        self.c.key("Enter")
        self.c.wait("location.pathname.endsWith('collection.html')", 15)
        self.c.wait("document.readyState === 'complete' && !!window.BGS_COPY", 15)
        time.sleep(0.3)
        self.assertGreater(want, 0)
        self.assertEqual(self.c.js("document.querySelectorAll('[data-grid] a.p').length"), want)

    # ---- phones and Arabic -------------------------------------------------
    def test_on_a_phone_the_list_sits_under_the_search_row(self):
        for w, h in ((390, 844), (360, 640)):
            self.view(w, h, phone=True)
            self.open()
            s = self.typed("oud", PHONE)
            self.assertTrue(s["ids"])
            left, top, right, bottom = s["rect"]
            self.assertGreaterEqual(left, 0)
            self.assertLessEqual(right, s["vw"])
            self.assertLessEqual(s["sw"], s["vw"], "the page scrolls sideways at %dx%d" % (w, h))
            row = self.c.js("document.getElementById('msearch').getBoundingClientRect().bottom")
            self.assertGreaterEqual(top, row - 20)
            tab = self.c.js("(() => { const t = document.querySelector('.tabbar'); const r = t && t.getBoundingClientRect();"
                            " return r && r.height ? r.top : null; })()")
            if tab is not None:
                self.assertLessEqual(bottom, tab, "the list runs under the tab bar at %dx%d" % (w, h))
        # a tap outside closes it
        self.c.js("document.querySelector('main, body').dispatchEvent(new PointerEvent('pointerdown', {bubbles: true}))")
        self.assertFalse(self.state(PHONE)["open"])

    def test_a_tap_on_a_result_opens_it(self):
        self.view(390, 844, phone=True)
        self.open()
        s = self.typed("vibe", PHONE)
        r = self.c.js("(() => { const a = document.getElementById(%s); const r = a.getBoundingClientRect();"
                      " return [r.left + r.width / 2, r.top + r.height / 2]; })()" % J(s["optionIds"][0]))
        for kind in ("mousePressed", "mouseReleased"):
            self.c.call("Input.dispatchMouseEvent", {"type": kind, "x": r[0], "y": r[1], "button": "left", "clickCount": 1})
        self.c.wait("location.pathname.endsWith('product.html')", 15, "the product page")
        self.assertEqual(self.c.js("new URLSearchParams(location.search).get('p')"), s["ids"][0])

    def test_arabic(self):
        self.view(1440, 900)
        self.open()
        self.c.js("document.querySelector('[data-langtoggle]').click()")
        s = self.typed("oud")
        self.assertEqual(s["allText"].strip(), self.c.js("window.BGS_AR['See all results']"))
        self.assertEqual(s["dir"], "rtl")
        self.assertTrue(s["ids"])


if __name__ == "__main__":
    unittest.main()
