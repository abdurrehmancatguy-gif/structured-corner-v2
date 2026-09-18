"""Store rules: settings.store reaches the page text and window.BGS_RULES,
the ladder and the cutoff are checked, checkout's numbers stay locked, and
site text that restates a rule wrongly is flagged without blocking the save.

    ADMIN_RULES_PORT=4741 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_rules.py'
"""
import copy
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from box import Box

PORT = int(os.environ.get("ADMIN_RULES_PORT", "4741"))


def rules_in(flow):
    js = (flow / "assets" / "catalogue.js").read_text(encoding="utf-8")
    return json.loads(re.search(r"^window\.BGS_RULES = (.*);$", js, re.M).group(1))


class RulesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)
        cls.flow = cls.b.repo / "flow"

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def settings(self):
        st, d = self.b.api("GET", "documents/settings")
        self.assertEqual(st, 200)
        return d["data"], d["rev"]

    def put_settings(self, change):
        data, rev = self.settings()
        change(data["store"])
        return self.b.api("PUT", "documents/settings", {"data": data}, rev=rev)

    def restore(self, data):
        _, rev = self.settings()
        st, res = self.b.api("PUT", "documents/settings", {"data": data}, rev=rev)
        self.assertEqual(st, 200, res)

    def page(self, name):
        return (self.flow / name).read_text(encoding="utf-8")

    def test_free_delivery_reaches_rules_and_page_text(self):
        before, _ = self.settings()
        st, res = self.put_settings(lambda s: s.update(free_delivery_over=200))
        try:
            self.assertEqual(st, 200, res)
            self.assertEqual(rules_in(self.flow)["free_delivery_over"], 200)
            home = self.page("index.html")
            self.assertIn("Free UAE delivery over AED 200", home)
            self.assertIn("free over AED 200.", home)
            product = self.page("product.html")
            # the line is page text now (pages.json), with the middle dot as a character
            self.assertIn("Free over AED 200 %s same-day before 2 PM" % chr(0xb7), product)   # pages.json, unchanged here
            self.assertIn("Free over AED 200. AED 12 below that.", product)
            self.assertIn("<span>Free UAE delivery over AED 200</span><b data-p1lb", self.page("cart.html"))
            # checkout prints the rules, so it follows the new threshold too
            self.assertIn("free over AED 200", self.page("checkout.html"))
            # the promises under the banner still say 150: named, not blocking. The
            # top strip writes the rule as {free_over}, so it follows and is not named.
            paths = {w["path"] for w in res["warnings"] if w["code"] == "stale_rule"}
            self.assertEqual(paths, {"/usp/0/title"})
            # and no page keeps a number of its own to fall behind
            self.assertEqual([w for w in res["warnings"] if w["code"] == "locked_page"], [])
        finally:
            self.restore(before)
        self.assertEqual(rules_in(self.flow)["free_delivery_over"], 150)

    def test_ladder_gift_box_cutoff_and_stock_reach_the_pages(self):
        before, _ = self.settings()
        self.assertIn('badge low">4 left', self.page("index.html"))

        def change(s):
            s["volume_ladder"] = [{"units": 2, "percent": 5}, {"units": 4, "percent": 10}, {"units": 8, "percent": 20}]
            s["gift_with_purchase"] = {"threshold": 400, "label": "Rose attar, 3 ml"}
            s.update(giftbox_fee=30, giftbox_volume_discount_at=2, giftbox_volume_discount_percent=15,
                     low_stock_at=3, sameday_cutoff="3:30 PM", delivery_fee=15, sameday_fee=30)
        st, res = self.put_settings(change)
        try:
            self.assertEqual(st, 200, res)
            r = rules_in(self.flow)
            self.assertEqual(r["volume_ladder"][2], {"units": 8, "percent": 20})
            self.assertEqual(r["sameday_cutoff_minutes"], 15 * 60 + 30)
            self.assertEqual(r["gift_with_purchase"], {"threshold": 400, "label": "Rose attar, 3 ml"})
            self.assertEqual(r["low_stock_at"], 3)
            cart = self.page("cart.html")
            for s in ("<span>Free rose attar over AED 400</span>", "<span data-p3txt>Add 2 more items to save 10%</span>",
                      ">2 of 4</b>", 'data-p3 style="width:50%"', "<b data-tierpct>5</b>"):
                self.assertIn(s, cart)
            box = self.page("gift-box.html")
            self.assertIn("<span>Premium box</span><span>AED 30</span>", box)
            self.assertIn("<span>Volume discount at 2 items</span><span>&minus;15%</span>", box)
            product = self.page("product.html")
            self.assertIn("same-day before 3:30 PM", product)
            self.assertIn("AED 15 below that.", product)
            self.assertIn("AED 30, for orders placed before the 3:30 PM cutoff.", product)
            self.assertIn("Order by 3:30 PM for delivery today in Dubai", self.page("index.html"))
            pages = "".join(self.page(n) for n in ("index.html", "collection.html", "product.html", "gift-box.html"))
            self.assertNotRegex(pages, r'badge low">[45] left')
            # the delivery fee, same-day fee and cutoff now differ from the promises under the banner
            rules = {w["rule"] for w in res["warnings"] if w["code"] == "stale_rule"}
            self.assertTrue({"delivery_fee", "sameday_fee", "sameday_cutoff"} <= rules, rules)
            self.assertEqual([w for w in res["warnings"] if w["code"] == "locked_page"], [])
        finally:
            self.restore(before)

    def test_gift_bar_keeps_a_proper_name_capital(self):
        before, _ = self.settings()
        try:
            st, res = self.put_settings(lambda s: s.update(
                gift_with_purchase={"threshold": 300, "label": "Royal Amber sample, 3 ml"}))
            self.assertEqual(st, 200, res)
            self.assertIn("<span>Free Royal Amber sample over AED 300</span>", self.page("cart.html"))
            # a phrase that is lower case after the first word still lower-cases
            st, res = self.put_settings(lambda s: s.update(
                gift_with_purchase={"threshold": 300, "label": "Mystery oud, 3 ml"}))
            self.assertEqual(st, 200, res)
            self.assertIn("<span>Free mystery oud over AED 300</span>", self.page("cart.html"))
        finally:
            self.restore(before)

    def test_locked_pages_print_the_rules_rather_than_their_own_numbers(self):
        # checkout and the order-confirmed page are locked with payments, but
        # their delivery rows come from the rules, so lint has nothing to hold
        # them to (lint.LOCKED_PAGES is empty) and neither can fall behind
        checkout = self.page("checkout.html")
        for s in ("free over AED 150</span><span>AED 12 below", "<b>Dispatch</b></span><span>1 to 3 business days"):
            self.assertIn(s, checkout)
        self.assertIn("Free over AED 150 &middot; dispatched in 1 to 3 business days", self.page("confirmed.html"))
        data, rev = self.settings()
        data["store"]["name"] = data["store"]["name"] + " "
        st, res = self.b.api("PUT", "documents/settings", {"data": data}, rev=rev)
        try:
            self.assertEqual(st, 200, res)
            self.assertEqual([w for w in res["warnings"] if w["code"] == "locked_page"], [])
        finally:
            data["store"]["name"] = data["store"]["name"][:-1]
            self.restore(data)

    def test_ladder_and_cutoff_are_checked(self):
        cases = (([{"units": 3, "percent": 10}, {"units": 3, "percent": 15}], "/store/volume_ladder/1/units"),
                 ([{"units": 6, "percent": 10}, {"units": 3, "percent": 15}], "/store/volume_ladder/1/units"),
                 ([{"units": 3, "percent": 10}, {"units": 6, "percent": 10}], "/store/volume_ladder/1/percent"),
                 ([{"units": 3, "percent": 60}], "/store/volume_ladder/0/percent"),
                 ([], "/store/volume_ladder"),
                 ([{"units": i, "percent": i} for i in range(1, 6)], "/store/volume_ladder"))
        for rungs, path in cases:
            st, res = self.put_settings(lambda s: s.update(volume_ladder=rungs))
            self.assertEqual(st, 422, rungs)
            self.assertIn(path, [d["path"] for d in res["error"]["details"]], rungs)
        for cutoff in ("11:00 PM", "5:30 AM", "14:00"):
            st, res = self.put_settings(lambda s: s.update(sameday_cutoff=cutoff))
            self.assertEqual(st, 422, cutoff)
            self.assertIn("/store/sameday_cutoff", [d["path"] for d in res["error"]["details"]])
        st, res = self.put_settings(lambda s: s.update(free_delivery_over=2001))
        self.assertEqual(st, 422)
        self.assertEqual(rules_in(self.flow)["volume_ladder"], [{"units": 3, "percent": 10}, {"units": 6, "percent": 15}])

    def test_the_cutoff_takes_only_ascii_digits(self):
        # Python's \d also matches the Arabic-Indic digits (and int() reads
        # them), so 2:0 followed by an Arabic-Indic two would have been read
        # as 2:02 PM; the cutoff is written with the digits 0 to 9 only
        before = self.b.content("settings")
        st, res = self.put_settings(lambda s: s.update(sameday_cutoff="2:0" + chr(0x0662) + " PM"))
        self.assertEqual(st, 422, res)
        self.assertEqual([(d["path"], d["code"]) for d in res["error"]["details"]], [("/store/sameday_cutoff", "format")])
        self.assertEqual(self.b.content("settings"), before)

    def test_box_discount_threshold_cannot_exceed_the_box(self):
        before, _ = self.settings()
        try:
            # the biggest box holds six scents, so a threshold above six could
            # never apply and is refused
            st, res = self.put_settings(lambda s: s.update(giftbox_volume_discount_at=8))
            self.assertEqual(st, 422, res)
            self.assertIn("/store/giftbox_volume_discount_at", [d["path"] for d in res["error"]["details"]])
            # six itself is allowed
            st, res = self.put_settings(lambda s: s.update(giftbox_volume_discount_at=6))
            self.assertEqual(st, 200, res)
            self.assertEqual(rules_in(self.flow)["giftbox_volume_discount_at"], 6)
        finally:
            self.restore(before)

    def test_cash_on_delivery_and_vat_stay_locked(self):
        # the values themselves are what the published policies say: no cash on
        # delivery and no VAT, so a change away from them is what is refused
        for key, value in (("cod_max_order", 400), ("cod_fee", 5), ("vat_rate_percent", 5), ("vat_inclusive", True)):
            st, res = self.put_settings(lambda s: s.update({key: value}))
            self.assertEqual(st, 403, key)
            self.assertEqual(res["error"]["code"], "locked_field")
        self.assertEqual(self.b.content("settings")["store"]["cod_max_order"], 300)

    def test_stale_usp_line_warns_but_saves(self):
        st, d = self.b.api("GET", "documents/copy")
        self.assertEqual(st, 200)
        original = copy.deepcopy(d["data"])
        d["data"]["usp"][0]["title"] = "Free delivery over AED 100"
        st, res = self.b.api("PUT", "documents/copy", {"data": d["data"]}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        stale = [w for w in res["warnings"] if w["code"] == "stale_rule"]
        self.assertEqual([(w["path"], w["rule"]) for w in stale], [("/usp/0/title", "free_delivery_over")])
        self.assertIn("AED 150", stale[0]["message"])
        self.assertIn("Promises under the banner, entry 1", stale[0]["message"])
        st, res = self.b.api("PUT", "documents/copy", {"data": original}, rev=res["rev"])
        self.assertEqual(st, 200, res)
        self.assertEqual([w for w in res["warnings"] if w["code"] == "stale_rule"], [])

    def test_build_falls_back_for_missing_rules_and_stops_on_bad_ones(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgsrules-"))
        try:
            flow = tmp / "flow"
            shutil.copytree(str(self.flow), str(flow), ignore=shutil.ignore_patterns(".backups", "*.tmp"))
            path = flow / "content" / "settings.json"
            s = json.loads(path.read_text(encoding="utf-8"))
            for k in ("volume_ladder", "gift_with_purchase", "low_stock_at"):
                del s["store"][k]
            path.write_text(json.dumps(s, indent=2), encoding="utf-8")
            p = subprocess.run([sys.executable, "build.py"], cwd=str(flow), capture_output=True, text=True, timeout=100)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(rules_in(flow), rules_in(self.flow))
            self.assertEqual((flow / "cart.html").read_text(encoding="utf-8"), self.page("cart.html"))
            s["store"]["volume_ladder"] = [{"units": 6, "percent": 10}, {"units": 3, "percent": 15}]
            path.write_text(json.dumps(s, indent=2), encoding="utf-8")
            p = subprocess.run([sys.executable, "build.py"], cwd=str(flow), capture_output=True, text=True, timeout=100)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("settings.store: volume_ladder", p.stderr)
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
