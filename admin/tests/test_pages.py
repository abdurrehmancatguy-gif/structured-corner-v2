"""Page text: pages.json reaches the built pages and window.BGS_COPY, its
tokens are filled from the store rules and the products, and text the
storefront cannot print safely is refused before anything is written.

    ADMIN_PAGES_PORT=4743 ADMIN_PAGES2_PORT=4744 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_pages.py'

The first class covers the shared shell, the homepage bands and the
collection and product pages; the second the gift box, bag, tracking,
corporate, account and 404 pages and the page groups the Pages screen lists.
Each runs its own server, so neither sees the other's edits.
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
import cdp_pipe

PORT = int(os.environ.get("ADMIN_PAGES_PORT", "4743"))
PORT2 = int(os.environ.get("ADMIN_PAGES2_PORT", "4744"))
GROUPS = {"Header and footer", "Homepage bands", "Collection", "Product page", "Gift box", "Bag", "Track order",
          "Corporate", "Account", "Legal pages", "404"}


def global_in(flow, name):
    js = (flow / "assets" / "catalogue.js").read_text(encoding="utf-8")
    return json.loads(re.search(r"^window\.%s = (.*);$" % name, js, re.M).group(1))


class _Pages:
    """A server on a clone of its own, and the helpers both classes use."""
    PORT = None

    @classmethod
    def setUpClass(cls):
        cls.b = Box(cls.PORT)
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

    def refused(self, cases, page):
        """Each change is refused with its code, and nothing is written."""
        stored = (self.flow / "content" / "pages.json").read_bytes()
        built = self.page(page)
        for code, change in cases:
            st, res = self.put(change)
            self.assertEqual(st, 422, (code, res))
            self.assertIn(code, [e["code"] for e in res["error"]["details"]], res)
        self.assertEqual((self.flow / "content" / "pages.json").read_bytes(), stored)
        self.assertEqual(self.page(page), built)

    def broken_build(self, change):
        """Build a copy of the site with pages.json changed; return the
        failed build's messages and whether any output file changed."""
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgspages-"))
        try:
            flow = tmp / "flow"
            shutil.copytree(str(self.flow), str(flow), ignore=shutil.ignore_patterns(".backups", "*.tmp"))
            path = flow / "content" / "pages.json"
            d = json.loads(path.read_text(encoding="utf-8"))
            change(d)
            path.write_text(json.dumps(d, indent=2), encoding="utf-8")
            outs = ("index.html", "cart.html", "account.html", "404.html", "assets/catalogue.js")
            before = {n: (flow / n).read_bytes() for n in outs}
            p = subprocess.run([sys.executable, "build.py"], cwd=str(flow), capture_output=True, text=True, timeout=100)
            self.assertNotEqual(p.returncode, 0)
            return p.stderr, [n for n in outs if (flow / n).read_bytes() != before[n]]
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


class PagesTests(_Pages, unittest.TestCase):
    PORT = PORT

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
        # rows and lines hold their own values: /promos/0/title, /legal/terms/body/3
        rows = [f["path"] for f in fields if f["type"] in ("rows", "lines")]
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
            d["index"]["families"]["oud-and-woods"]["label"] = "Oud, woods & resin"
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
            self.assertIn("<b>Oud, woods &amp; resin</b></a>", home)
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

    def test_the_discovery_band_product_cannot_be_deleted(self):
        st, p = self.b.api("GET", "products/discovery-trio")
        self.assertEqual(st, 200, p)
        self.assertIn({"where": "Pages, Homepage bands, Discovery band", "link": "#/content/pages/home"}, p["refs"])
        stored = (self.flow / "content" / "pages.json").read_bytes()
        st, res = self.b.api("DELETE", "products/discovery-trio", rev=p["rev"])
        self.assertEqual((st, res["error"]["code"]), (409, "referenced"), res)
        self.assertIn("discovery-trio", self.b.content("products"))
        self.assertEqual((self.flow / "content" / "pages.json").read_bytes(), stored)

    def test_rules_legal_name_and_title_suffix_come_from_settings(self):
        st, d = self.b.api("GET", "documents/settings")
        before = copy.deepcopy(d["data"])
        d["data"]["store"].update(free_delivery_over=175, delivery_fee=20, dispatch_days="2 to 4 business days",
                                  legal_name="BGS Test Trading")
        d["data"]["seo"]["default_title_suffix"] = "BGS"
        st, res = self.b.api("PUT", "documents/settings", {"data": d["data"]}, rev=d["rev"])
        try:
            self.assertEqual(st, 200, res)
            prod = self.page("product.html")
            # the rules reach the product page's delivery rows and its facts
            self.assertIn("Dispatched in 2 to 4 business days", prod)
            self.assertIn("Free over AED 175 \u00b7 dispatch in 2 to 4 business days</span>", prod)
            self.assertIn("Free over AED 175. AED 20 below that. UAE only.", prod)
            coll = self.page("collection.html")
            self.assertIn("Orders are dispatched in 2 to 4 business days, UAE wide", coll)
            self.assertIn("<title>Your Bag | BGS</title>", self.page("cart.html"))
            self.assertIn("<p>BGS Test Trading &middot; Dubai, UAE</p>", coll)
            self.assertIn("&copy; 2026 BGS Test Trading</span>", coll)
            self.assertEqual(global_in(self.flow, "BGS_COPY")["title_suffix"], "BGS")
        finally:
            st, d2 = self.b.api("GET", "documents/settings")
            self.assertEqual(self.b.api("PUT", "documents/settings", {"data": before}, rev=d2["rev"])[0], 200)

    def test_contact_details_replace_the_footer_placeholder(self):
        # The shop has an address now, so the placeholder is what emptying the
        # three contact lines leaves behind, not what the page starts with.
        before = self.doc()["data"]
        slot = '<p><span class="slot">address, hours, phone</span></p>'
        try:
            st, res = self.put(lambda d: d["shell"]["footer"]["contact"].update(address="", hours="", phone=""))
            self.assertEqual(st, 200, res)
            home = self.page("index.html")
            self.assertIn(slot, home)
            self.assertNotIn('<div class="footmap">', home)      # a map of nowhere is no map
            st, res = self.put(lambda d: d["shell"]["footer"]["contact"].update(address="Test address", hours="Test hours"))
            self.assertEqual(st, 200, res)
            home = self.page("index.html")
            self.assertIn("<p>Test address &middot; Test hours</p>", home)
            self.assertNotIn(slot, home)
            self.assertIn("maps.google.com/maps?q=Test%20address&amp;output=embed", home)
        finally:
            self.restore(before)
        self.assertNotIn(slot, self.page("index.html"))

    @unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
    def test_spaces_around_the_stock_and_batch_labels_keep_their_rows(self):
        # shop.js finds these rows by their label, which the page prints as typed
        pr = self.b.content("products")["be-mine"]
        self.assertTrue(pr["barcode"] and pr["stock"] > 5, pr)
        before = self.doc()["data"]
        st, res = self.put(lambda d: d["product"]["specs"].update(availability="Availability ", batch=" Batch number"))
        self.assertEqual(st, 200, res)
        c = cdp_pipe.Chrome()
        try:
            c.go("http://localhost:%d/product.html?p=be-mine" % self.PORT)
            c.wait("document.readyState === 'complete' && !!window.BGS_COPY", 30)
            rows = c.js("[...document.querySelectorAll('[data-specs] > div')].filter((r) => !r.hidden)"
                        ".map((r) => [r.firstElementChild.textContent.trim(), r.lastElementChild.textContent.trim()])")
            self.assertIn(["Availability", "In stock"], rows)
            self.assertIn(["Barcode", pr["barcode"]], rows)
            self.assertEqual(c.errors(), [])
        finally:
            c.close()
            self.restore(before)

    # ---- what is refused ------------------------------------------------------------

    def test_a_link_to_a_product_that_does_not_exist_is_refused(self):
        st, res = self.put(lambda d: d["index"]["promos"][0].update(href="product.html?p=ghost"))
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/index/promos/0/href", "unknown_product")])
        self.refused([("unknown_product", lambda d: d["index"]["discovery_band"].update(cta_href="product.html?p=ghost&tab=apply"))],
                     "index.html")

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


KEYS = ["shell", "home", "collection", "product", "gift-box", "bag", "track-order", "corporate", "account",
        "legal", "404", "checkout", "confirmed"]


class PagesPartTwoTests(_Pages, unittest.TestCase):
    PORT = PORT2

    def test_the_groups_list_every_page_in_order(self):
        st, s = self.b.api("GET", "schema")
        self.assertEqual(st, 200)
        res = s["resources"]["pages"]
        groups = res["resource"]["groups"]
        self.assertEqual([g["key"] for g in groups], KEYS)
        used = {f["group"] for f in res["fields"]}
        for g in groups:
            self.assertTrue(g["label"] and g["about"], g)
            self.assertTrue((self.flow / g["page"]).is_file(), g)
            if g["key"] in ("checkout", "confirmed"):
                self.assertEqual(g["locked"], "Changed by a developer in code")
                self.assertNotIn(g["label"], used)
            else:
                self.assertNotIn("locked", g)
        self.assertEqual(used, {g["label"] for g in groups if not g.get("locked")})
        self.assertEqual(used, GROUPS)

    def test_an_edit_reaches_the_part_two_pages_and_the_shop_script(self):
        names = ("gift-box.html", "cart.html", "track-order.html", "corporate.html", "account.html", "404.html")
        before, pages = self.doc()["data"], {n: self.page(n) for n in names}

        def change(d):
            d["gift_box"]["title"] = "Fill a box"
            d["gift_box"]["size_label"] = "{n} scents"
            d["gift_box"]["summary"]["fill_many"] = "{n} to fill"
            d["gift_box"]["options"][1]["highlight"] = False
            d["gift_box"]["options"].append({"label": "Test option", "value": "Off", "highlight": True})
            d["cart"]["title"] = "Your basket"
            d["cart"]["progress"]["gift"] = "{gift} free from {gift_over}"
            d["cart"]["summary"]["free"] = "No charge"
            d["cart"]["items"]["many"] = "{n} things"
            d["track"]["form"]["number"] = "Order no."
            d["track"]["stages"][0]["body"] = "Order received"
            d["track"]["stages"].append({"label": "Test stage", "body": "Test text"})
            d["corporate"]["tiers"].pop()
            d["corporate"]["form"]["email"] = "Email"
            d["corporate"]["replies"]["thanks_name"] = "Thanks, {name}"
            d["account"]["programme"] = "BGS Club"
            d["account"]["loyalty"]["tiers"][0]["name"] = "First"
            d["account"]["consent"]["language"] = "English"
            d["not_found"]["heading"] = "Nothing here"
            d["not_found"]["button"] = "Home"
        st, res = self.put(change)
        try:
            self.assertEqual(st, 200, res)
            box = self.page("gift-box.html")
            self.assertIn('<h2 class="pagetitle">Fill a box</h2>', box)
            self.assertIn('data-boxsize="6">6 scents</button>', box)
            self.assertIn('data-boxcta style="margin-top:12px">3 to fill</button>', box)
            self.assertIn("<div><span>QR video message %s 60s</span><span>Free</span></div>" % chr(0xB7), box)
            self.assertIn('<div><span>Test option</span><span style="color:var(--green);font-weight:600">Off</span></div>', box)
            cart = self.page("cart.html")
            self.assertIn('<h2 class="pagetitle">Your basket<span data-bagitems></span></h2>', cart)
            self.assertIn("<span>mystery oud free from AED 300</span>", cart)
            self.assertIn('<span data-delivery style="color:var(--green)">No charge</span>', cart)
            track = self.page("track-order.html")
            self.assertIn('aria-label="Order no." placeholder="Order no."', track)
            self.assertIn("<div><span>Placed</span><span>Order received</span></div>", track)
            self.assertIn("<div><span>Test stage</span><span>Test text</span></div>", track)
            corp = self.page("corporate.html")
            self.assertEqual(corp.count('<div class="tier">'), 3)
            self.assertIn('aria-label="Email" placeholder="Email"', corp)
            acct = self.page("account.html")
            self.assertIn('<span class="eyebrow gold-d">BGS Club</span><b>First</b>', acct)
            self.assertIn('<a href="account.html">BGS Club &amp; wallet</a>', acct)
            self.assertIn('<div class="t on"><b>First</b>', acct)
            self.assertIn("<span>Language</span><span>English</span>", acct)
            nf = self.page("404.html")
            self.assertIn("<h1>Nothing here</h1>", nf)
            self.assertIn('<a id="home" href="/">Home</a>', nf)
            js = global_in(self.flow, "BGS_COPY")
            self.assertEqual(js["cart"]["summary"]["free"], "No charge")
            self.assertEqual(js["cart"]["items"]["many"], "{n} things")
            self.assertEqual(js["corporate"]["replies"]["thanks_name"], "Thanks, {name}")
            self.assertEqual(js["gift_box"]["summary"]["fill_many"], "{n} to fill")
        finally:
            self.restore(before)
        for n in names:
            self.assertEqual(self.page(n), pages[n], n)

    def test_every_text_the_shop_script_reads_is_in_its_data(self):
        # shop.js keeps its own copy of each text for a page with an older
        # catalogue.js, so a path the data does not have would leave a Pages
        # field saving without ever reaching the shop.
        shop = (self.flow / "assets" / "shop.js").read_text(encoding="utf-8")
        js = global_in(self.flow, "BGS_COPY")
        calls = re.findall(r'bgsCopy(?:Html)?\(\s*"([^"]+)"\s*([,+])', shop)
        self.assertGreater(len(calls), 40)
        for path, joined in calls:
            node = js
            for part in path.rstrip(".").split("."):
                self.assertIsInstance(node, dict, path)
                self.assertIn(part, node, path)
                node = node[part]
            # a path shop.js finishes with a variable names a group of texts
            self.assertIsInstance(node, dict if joined == "+" else str, path)

    @unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
    def test_saving_one_page_over_a_newer_copy_keeps_the_other_pages(self):
        before = self.doc()["data"]
        c = cdp_pipe.Chrome()
        try:
            c.go("http://localhost:%d/admin/#/content/pages/bag" % self.PORT)
            c.wait("!!document.querySelector('.pg-form')", 30)
            # the homepage bands are saved somewhere else while the bag is open
            st, res = self.put(lambda d: d["index"]["discovery_band"].update(eyebrow="Begin here"))
            self.assertEqual(st, 200, res)
            c.js("""(() => { const l = [...document.querySelectorAll('label.f-label')]
                       .find((x) => x.textContent.trim().startsWith('Checkout button'));
                     const i = document.getElementById(l.htmlFor); i.value = 'Go to checkout';
                     i.dispatchEvent(new Event('input', { bubbles: true })); })()""")
            c.wait("[...document.querySelectorAll('button')].some((b) => b.textContent.trim() === 'Save')", 10)
            c.js("[...document.querySelectorAll('button')].filter((b) => b.textContent.trim() === 'Save').pop().click()")
            mine = "[...document.querySelectorAll('.dlg-actions button')].find((b) => b.textContent.trim() === 'Save mine over it')"
            c.wait("!!" + mine, 40)
            c.js(mine + ".click()")
            c.wait("[...document.querySelectorAll('.toast')].some((t) => /Saved/.test(t.textContent))", 60)
            data = self.b.content("pages")
            self.assertEqual(data["cart"]["summary"]["checkout"], "Go to checkout")
            self.assertEqual(data["index"]["discovery_band"]["eyebrow"], "Begin here")
            self.assertIn("Begin here", self.page("index.html"))
            self.assertEqual(c.errors(), [])
        finally:
            c.close()
            self.restore(before)

    @unittest.skipUnless(os.path.exists(cdp_pipe.CHROME), "headless Chrome is not installed")
    def test_every_page_fits_a_phone(self):
        st, s = self.b.api("GET", "schema")
        groups = [g for g in s["resources"]["pages"]["resource"]["groups"] if not g.get("locked")]
        c = cdp_pipe.Chrome(width=390)
        try:
            c.go("http://localhost:%d/admin/#/content/pages" % self.PORT)
            c.wait("!!document.querySelector('.pg-list')", 30)
            self.assertEqual(c.js("document.documentElement.scrollWidth"), 390)
            for g in groups:
                c.go("http://localhost:%d/admin/#/content/pages/%s" % (self.PORT, g["key"]))
                c.wait("!!document.querySelector('.pg-form') && document.querySelector('main h1').textContent === %s"
                       % json.dumps(g["label"]), 25)
                self.assertEqual(c.js("document.documentElement.scrollWidth"), 390, g["key"])
            self.assertEqual(c.errors(), [])
        finally:
            c.close()

    def test_the_404_title_ends_with_the_settings_suffix(self):
        self.assertIn("<title>Page not found | BGS Corner</title>", self.page("404.html"))
        st, d = self.b.api("GET", "documents/settings")
        before = copy.deepcopy(d["data"])
        d["data"]["seo"]["default_title_suffix"] = "BGS"
        st, res = self.b.api("PUT", "documents/settings", {"data": d["data"]}, rev=d["rev"])
        try:
            self.assertEqual(st, 200, res)
            self.assertIn("<title>Page not found | BGS</title>", self.page("404.html"))
        finally:
            st, d2 = self.b.api("GET", "documents/settings")
            self.assertEqual(self.b.api("PUT", "documents/settings", {"data": before}, rev=d2["rev"])[0], 200)
        self.assertIn("<title>Page not found | BGS Corner</title>", self.page("404.html"))

    def test_part_two_text_the_pages_cannot_print_is_refused(self):
        self.refused([
            ("format", lambda d: d["gift_box"].update(size_label="slots")),
            ("format", lambda d: d["cart"]["progress"].update(to_go="to go")),
            ("format", lambda d: d["cart"]["progress"].update(gift="Free {gift} before {cutoff}")),
            ("format", lambda d: d["corporate"]["replies"].update(thanks_name="Thanks")),
            ("format", lambda d: d["track"]["replies"].update(looking="Looking for {order}")),
            ("markup", lambda d: d["not_found"].update(heading="<b>Gone</b>")),
            ("too_long", lambda d: d["account"].update(programme="B" * 31)),
            ("required", lambda d: d["cart"]["summary"].update(total=" ")),
            ("href", lambda d: d["account"]["orders"].update(cta_href="https://example.com/")),
            ("too_many", lambda d: d["account"]["loyalty"]["tiers"].append({"name": "Test", "note": "Test"})),
            ("too_few", lambda d: d["track"].update(stages=[])),
        ], "cart.html")

    def test_a_brace_in_text_that_takes_no_token_is_refused_on_its_field(self):
        # the build would either refuse it or print it as typed, so the save
        # refuses it first, next to the field
        self.refused([("format", change) for change in (
            lambda d: d["product"].update(voucher_note="A voucher on any bottle over {free_over}."),
            lambda d: d["corporate"]["replies"].update(thanks="Thank you {friend}"),
            lambda d: d["cart"]["line"].update(remove="Remove {x}"),
            lambda d: d["track"]["replies"].update(missing="Enter {query}"),
            lambda d: d["gift_box"]["summary"].update(full="Full {n}"),
            lambda d: d["cart"]["progress"].update(unlocked="Unlocked {free_over}"),
            lambda d: d["cart"]["summary"].update(free="Free {x}"),
            lambda d: d["track"]["stages"][0].update(body="Before {cutoff}"),
            lambda d: d["index"]["discovery_band"].update(body="Over {free_over}"),
            lambda d: d["shell"]["header"].update(bag="Bag }"),
        )], "cart.html")
        st, res = self.put(lambda d: d["corporate"]["replies"].update(thanks="Thank you {friend}"))
        self.assertIn({"path": "/corporate/replies/thanks", "code": "format",
                       "message": "This text takes no {tokens}; leave out braces."}, res["error"]["details"])

    def test_the_build_stops_on_a_brace_in_text_that_takes_no_token(self):
        # pages.json edited by hand, as a terminal or a Claude session can
        def change(d):
            d["product"]["voucher_note"] = "A voucher on any bottle over {free_over}."
            d["track"]["stages"][0]["body"] = "Before {cutoff}"
            d["product"]["share"]["copied"] = "Copied {x}"
            d["product"]["specs"]["in_stock"] = "{n} in stock"
            d["cart"]["summary"]["free"] = "Free {x}"
            d["collection"]["genders"]["Him"] = "Him }"
        err, changed = self.broken_build(change)
        for msg in ("pages.json product.voucher_note has {free_over}, which it cannot use",
                    "pages.json track.stages.0.body has {cutoff}, which it cannot use",
                    "pages.json product.share.copied has {x}, which it cannot use",
                    "pages.json product.specs.in_stock has {n}, which it cannot use",
                    "pages.json cart.summary.free has {x}, which it cannot use",
                    "pages.json collection.genders.Him has a brace that is not part of a {token}"):
            self.assertIn(msg, err)
        self.assertEqual(changed, [])

    def test_the_build_stops_on_broken_part_two_text_before_writing(self):
        def change(d):
            del d["gift_box"]["title"]
            del d["cart"]["line"]["remove"]
            d["cart"]["items"]["one"] = "One item"
            d["corporate"]["replies"]["quote_units"] = "A quote for {units}"
            d["gift_box"]["options"][0]["highlight"] = "yes"
            del d["not_found"]["heading"]
        err, changed = self.broken_build(change)
        for msg in ("pages.json gift_box.title must be text", "pages.json cart.line.remove must be text",
                    "pages.json cart.items.one must contain {n}",
                    "pages.json corporate.replies.quote_units has {units}, which it cannot use",
                    "pages.json gift_box.options.0.highlight must be true or false",
                    "pages.json not_found.heading must be text"):
            self.assertIn(msg, err)
        # read twice (its tokens checked, then its text kept), named once
        self.assertEqual(err.count("pages.json cart.line.remove must be text"), 1)
        self.assertEqual(changed, [])

    def test_the_added_to_bag_panel_and_the_phone_checkout_bar_take_the_bag_words(self):
        # the panel after every Add reads its words, and the summary's
        # Subtotal and Checkout, from BGS_COPY; the bag page prints the phone
        # checkout bar with the summary's Total and Checkout
        data = self.doc()["data"]
        self.assertEqual(global_in(self.flow, "BGS_COPY")["cart"]["added"], data["cart"]["added"])
        before, cart = data, self.page("cart.html")

        def change(d):
            d["cart"]["added"].update(title="In your bag", qty="{n} in the bag", view_bag="See the bag",
                                      close="Shut", button="In the bag")
            d["cart"]["summary"].update(subtotal="Items", total="To pay", checkout="Pay now")
        st, res = self.put(change)
        try:
            self.assertEqual(st, 200, res)
            js = global_in(self.flow, "BGS_COPY")["cart"]
            self.assertEqual(js["added"], {"title": "In your bag", "qty": "{n} in the bag", "view_bag": "See the bag",
                                           "close": "Shut", "button": "In the bag"})
            self.assertEqual((js["summary"]["subtotal"], js["summary"]["checkout"]), ("Items", "Pay now"))
            page = self.page("cart.html")
            self.assertIn('href="checkout.html" data-checkout style="margin-top:12px">Pay now</a>', page)
            self.assertIn('<div class="bagbar" data-bagbar aria-hidden="true"><div class="bb-t"><span>To pay</span>'
                          '<b data-bagbartotal>AED 0</b></div><a class="btn solid" href="checkout.html">Pay now</a></div>', page)
        finally:
            self.restore(before)
        self.assertEqual(self.page("cart.html"), cart)
        self.refused([
            ("format", lambda d: d["cart"]["added"].update(qty="Qty")),
            ("format", lambda d: d["cart"]["added"].update(view_bag="View {n}")),
            ("too_long", lambda d: d["cart"]["added"].update(title="B" * 41)),
            ("required", lambda d: d["cart"]["added"].update(button=" ")),
        ], "cart.html")

    def test_the_build_stops_on_broken_added_to_bag_words(self):
        def change(d):
            d["cart"]["added"]["qty"] = "Qty"
            del d["cart"]["added"]["view_bag"]
            d["cart"]["added"]["close"] = "Close {x}"
        err, changed = self.broken_build(change)
        for msg in ("pages.json cart.added.qty must contain {n}", "pages.json cart.added.view_bag must be text",
                    "pages.json cart.added.close has {x}, which it cannot use"):
            self.assertIn(msg, err)
        self.assertEqual(changed, [])


if __name__ == "__main__":
    unittest.main()
