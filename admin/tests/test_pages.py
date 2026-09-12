"""Page text: pages.json reaches the built pages and window.BGS_COPY, its
tokens are filled from the store rules and the products, and text the
storefront cannot print safely is refused before anything is written.

    ADMIN_PAGES_PORT=4743 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_pages.py'
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

PORT = int(os.environ.get("ADMIN_PAGES_PORT", "4743"))
GROUPS = {"Header and footer", "Homepage bands", "Collection", "Product page", "Gift box", "Bag", "Track order",
          "Corporate", "Account", "404"}


def global_in(flow, name):
    js = (flow / "assets" / "catalogue.js").read_text(encoding="utf-8")
    return json.loads(re.search(r"^window\.%s = (.*);$" % name, js, re.M).group(1))


class PagesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)
        cls.flow = cls.b.repo / "flow"

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def page(self, name):
        return (self.flow / name).read_text(encoding="utf-8")

    def doc(self):
        st, d = self.b.api("GET", "documents/pages")
        self.assertEqual(st, 200, d)
        return d

    def put(self, change):
        d = self.doc()
        data = copy.deepcopy(d["data"])
        change(data)
        return self.b.api("PUT", "documents/pages", {"data": data}, rev=d["rev"])

    def restore(self, data):
        st, res = self.b.api("PUT", "documents/pages", {"data": data}, rev=self.doc()["rev"])
        self.assertEqual(st, 200, res)

    # ---- the schema --------------------------------------------------------------

    def test_schema_describes_every_value_by_page(self):
        st, s = self.b.api("GET", "schema")
        self.assertEqual(st, 200)
        res = s["resources"]["pages"]
        self.assertEqual((res["resource"]["kind"], res["resource"]["label"]), ("document", "Pages"))
        self.assertTrue(res["resource"]["intro"])
        fields = res["fields"]
        self.assertEqual({f["group"] for f in fields}, GROUPS)
        for f in fields:
            self.assertTrue(f.get("label"), f["path"])
            if f["type"] in ("text", "textarea"):
                self.assertTrue(f.get("maxLength"), f["path"])
        for f in [f for f in fields if f["type"] == "rows"]:
            for g in f["fields"]:
                self.assertTrue(g.get("label") and (g["type"] in ("href", "bool") or g.get("maxLength")), g["path"])

        # every value in the file has a field, and every field a value
        def leaves(o, p=""):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield from leaves(v, p + "/" + k)
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    yield from leaves(v, "%s/%d" % (p, i))
            else:
                yield p
        data = self.doc()["data"]
        rows = [f["path"] for f in fields if f["type"] == "rows"]
        plain = {f["path"] for f in fields}
        for p in leaves(data):
            self.assertTrue(p in plain or any(p.startswith(r + "/") for r in rows), p)
        for p in plain:
            node = data
            for part in p.strip("/").split("/"):
                self.assertIn(part, node, p)
                node = node[part]

    def test_copy_and_settings_fields_the_pages_now_print_are_on_the_site(self):
        st, s = self.b.api("GET", "schema")
        by = {(n, f["path"]): f for n in ("copy", "settings") for f in s["resources"][n]["fields"]}
        for key in (("copy", "/strip/countdown_line"), ("copy", "/strip/right_links"), ("copy", "/search_placeholder"),
                    ("settings", "/store/legal_name"), ("settings", "/store/location"),
                    ("settings", "/seo/default_title_suffix")):
            self.assertNotEqual(by[key].get("rendered"), False, key)

    # ---- what the pages print ---------------------------------------------------

    def test_an_edit_reaches_the_pages_and_the_shop_script(self):
        names = ("index.html", "collection.html", "product.html", "cart.html")
        before, pages = self.doc()["data"], {n: self.page(n) for n in names}

        def change(d):
            d["shell"]["noscript"] = "Turn on JavaScript & come back."
            d["shell"]["header"]["wishlist"] = "Saved"
            d["shell"]["footer"]["newsletter"]["button"] = "Sign up"
            d["shell"]["footer"]["copyright_year"] = 2027
            d["index"]["promos"][1]["title"] = "Try 3 ml"
            d["index"]["families"]["oud-and-woods"] = "Oud, woods & resin"
            d["index"]["reels_link"]["label"] = "Every spray"
            d["collection"]["sort"]["name"] = "Name, A first"
            d["collection"]["count"] = "{n} found"
            d["collection"]["genders"]["Him"] = "For him"
            d["product"]["tabs"]["reviews"] = "What buyers say"
            d["product"]["delivery_rows"][0]["body"] = "Free from {free_over}, else {delivery_fee}."
            d["product"]["share"]["copied"] = "Copied"
            d["product"]["specs"]["only_left"] = "{n} to go"
        st, res = self.put(change)
        try:
            self.assertEqual(st, 200, res)
            for n in names:
                p = self.page(n)
                self.assertIn('<div class="nojs">Turn on JavaScript &amp; come back.</div>', p, n)
                self.assertIn("<span>Saved</span>", p, n)
                self.assertIn('<span class="btn">Sign up</span>', p, n)
                self.assertIn("&copy; 2027 BGS Corner General Trading LLC", p, n)
            home = self.page("index.html")
            self.assertIn("<b>Try 3 ml</b>", home)
            self.assertIn("<b>Oud, woods &amp; resin</b><span>", home)
            self.assertIn('<a href="collection.html?cat=edp">Every spray &rarr;</a>', home)
            coll = self.page("collection.html")
            self.assertIn('<option value="name">Name, A first</option>', coll)
            self.assertIn("<span data-count>34</span> found", coll)
            self.assertIn('value="Him">For him</label>', coll)
            prod = self.page("product.html")
            self.assertIn('aria-selected="false">What buyers say</button>', prod)
            self.assertIn("Free from AED 150, else AED 12.", prod)
            js = global_in(self.flow, "BGS_COPY")
            self.assertEqual(js["product"]["share"]["copied"], "Copied")
            self.assertEqual(js["product"]["specs"]["only_left"], "{n} to go")
            self.assertEqual(js["collection"]["genders"]["Him"], "For him")
        finally:
            self.restore(before)
        for n in names:
            self.assertEqual(self.page(n), pages[n], n)

    def test_the_discovery_band_follows_its_product(self):
        before = self.doc()["data"]
        prices = {k: self.b.content("products")[k]["price"] for k in ("discovery-trio", "his-and-hers-duo")}
        self.assertIn("<h3>Discovery Trio, AED {:,}</h3>".format(prices["discovery-trio"]), self.page("index.html"))
        st, res = self.put(lambda d: d["index"]["discovery_band"].update(product="his-and-hers-duo", heading="Two for {price}"))
        try:
            self.assertEqual(st, 200, res)
            self.assertIn("<h3>Two for AED {:,}</h3>".format(prices["his-and-hers-duo"]), self.page("index.html"))
        finally:
            self.restore(before)
        st, res = self.put(lambda d: d["index"]["discovery_band"].update(product="no-such-product"))
        self.assertEqual(st, 422, res)
        self.assertIn("unknown_product", [e["code"] for e in res["error"]["details"]])

    def test_rules_legal_name_and_title_suffix_come_from_settings(self):
        st, d = self.b.api("GET", "documents/settings")
        before = copy.deepcopy(d["data"])
        d["data"]["store"].update(sameday_fee=30, sameday_cutoff="3:30 PM", legal_name="BGS Test Trading")
        d["data"]["seo"]["default_title_suffix"] = "BGS"
        st, res = self.b.api("PUT", "documents/settings", {"data": d["data"]}, rev=d["rev"])
        try:
            self.assertEqual(st, 200, res)
            prod = self.page("product.html")
            self.assertIn("AED 30, for orders placed before the 3:30 PM cutoff.", prod)
            self.assertIn("same-day before 3:30 PM</span>", prod)
            coll = self.page("collection.html")
            self.assertIn("Order by 3:30 PM for delivery today in Dubai", coll)
            self.assertIn("<title>Your Bag | BGS</title>", self.page("cart.html"))
            self.assertIn("<p>BGS Test Trading &middot; Dubai, UAE</p>", coll)
            self.assertIn("&copy; 2026 BGS Test Trading</span>", coll)
            self.assertEqual(global_in(self.flow, "BGS_COPY")["title_suffix"], "BGS")
        finally:
            st, d2 = self.b.api("GET", "documents/settings")
            self.assertEqual(self.b.api("PUT", "documents/settings", {"data": before}, rev=d2["rev"])[0], 200)

    def test_contact_details_replace_the_footer_placeholder(self):
        before = self.doc()["data"]
        slot = '<p><span class="slot">address, hours, phone</span></p>'
        self.assertIn(slot, self.page("index.html"))
        st, res = self.put(lambda d: d["shell"]["footer"]["contact"].update(address="Test address", hours="Test hours"))
        try:
            self.assertEqual(st, 200, res)
            home = self.page("index.html")
            self.assertIn("<p>Test address &middot; Test hours</p>", home)
            self.assertNotIn(slot, home)
        finally:
            self.restore(before)
        self.assertIn(slot, self.page("index.html"))

    # ---- what is refused ------------------------------------------------------------

    def test_markup_long_dashes_and_stray_tokens_are_refused(self):
        stored = (self.flow / "content" / "pages.json").read_bytes()
        home = self.page("index.html")
        cases = [
            ("markup", lambda d: d["index"]["promos"][0].update(title="<b>Build</b> a box")),
            ("em_dash", lambda d: d["product"].update(apply_note="Oil based %s always." % chr(0x2014))),
            ("format", lambda d: d["product"]["delivery_rows"][1].update(body="Before {cutof}.")),
            ("format", lambda d: d["collection"].update(count="products")),
            ("format", lambda d: d["index"]["discovery_band"].update(heading="Trio {name}")),
            ("too_long", lambda d: d["shell"]["header"].update(bag="B" * 21)),
            ("required", lambda d: d["product"]["tabs"].update(reviews="  ")),
            ("href", lambda d: d["product"]["related"].update(link_href="https://example.com/")),
            ("too_small", lambda d: d["shell"]["footer"].update(copyright_year=1999)),
            ("format", lambda d: d["shell"]["footer"]["contact"].update(phone="call us")),
        ]
        for code, change in cases:
            st, res = self.put(change)
            self.assertEqual(st, 422, (code, res))
            self.assertIn(code, [e["code"] for e in res["error"]["details"]], res)
        st, res = self.put(lambda d: d["product"].update(extra="x"))
        self.assertEqual((st, res["error"]["code"]), (403, "not_editable"))
        # the strip in copy.json takes the rule tokens and nothing else
        st, d = self.b.api("GET", "documents/copy")
        d["data"]["strip"]["countdown_line"] = "Order by {time} for delivery today"
        st, res = self.b.api("PUT", "documents/copy", {"data": d["data"]}, rev=d["rev"])
        self.assertEqual((st, [e["code"] for e in res["error"]["details"]]), (422, ["format"]))
        self.assertEqual((self.flow / "content" / "pages.json").read_bytes(), stored)
        self.assertEqual(self.page("index.html"), home)

    def test_the_build_stops_on_missing_or_broken_page_text(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgspages-"))
        try:
            flow = tmp / "flow"
            shutil.copytree(str(self.flow), str(flow), ignore=shutil.ignore_patterns(".backups", "*.tmp"))
            path = flow / "content" / "pages.json"
            d = json.loads(path.read_text(encoding="utf-8"))
            del d["product"]["tabs"]["reviews"]
            d["collection"]["count"] = "products"
            d["product"]["delivery_rows"][0]["body"] = "Free over {free}."
            d["index"]["discovery_band"]["product"] = "no-such-product"
            path.write_text(json.dumps(d, indent=2), encoding="utf-8")
            before = (flow / "index.html").read_bytes()
            p = subprocess.run([sys.executable, "build.py"], cwd=str(flow), capture_output=True, text=True, timeout=100)
            self.assertNotEqual(p.returncode, 0)
            for msg in ("pages.json product.tabs.reviews must be text", "pages.json collection.count must contain {n}",
                        "pages.json product.delivery_rows.0.body has {free}, which it cannot use",
                        "pages.json index.discovery_band.product names no product"):
                self.assertIn(msg, p.stderr)
            self.assertEqual((flow / "index.html").read_bytes(), before)
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
