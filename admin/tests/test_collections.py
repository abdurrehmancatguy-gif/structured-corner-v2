"""Collections: each category's words, circle and homepage shelf are one view
saved in one transaction, the shop reads its category text and shelves from
content, and the view refuses what it does not own.

    ADMIN_COLLECTIONS_PORT=4742 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_collections.py'
"""
import copy
import html
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

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "devtools"))
import dom_diff  # noqa: E402
import cdp_pipe  # noqa: E402

PORT = int(os.environ.get("ADMIN_COLLECTIONS_PORT", "4742"))
KEYS = ["attars", "bakhoor", "edp", "gift-sets", "all"]


def global_in(flow, name):
    js = (flow / "assets" / "catalogue.js").read_text(encoding="utf-8")
    return json.loads(re.search(r"^window\.%s = (.*);$" % name, js, re.M).group(1))


def shelf_html(home, cat):
    """The homepage section whose see-all link opens cat, heading to end."""
    m = re.search(r'<div class="sec-h"><h2>[^<]*</h2><a href="collection\.html\?cat=%s">.*?</section>' % re.escape(cat),
                  home, re.S)
    return m.group(0) if m else ""


class CollectionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)
        cls.flow = cls.b.repo / "flow"

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def page(self, name):
        return (self.flow / name).read_text(encoding="utf-8")

    def one(self, key):
        st, d = self.b.api("GET", "collections/" + key)
        self.assertEqual(st, 200, d)
        return d

    def put(self, key, change, rev=None):
        d = self.one(key)
        data = copy.deepcopy(d["data"])
        change(data)
        return self.b.api("PUT", "collections/" + key, {"data": data}, rev=rev or d["rev"])

    def restore(self, key, data):
        st, res = self.b.api("PUT", "collections/" + key, {"data": data}, rev=self.one(key)["rev"])
        self.assertEqual(st, 200, res)

    def published(self, cat=None):
        return [k for k, d in self.b.content("products").items()
                if d.get("published", True) and (cat is None or d.get("category") == cat)]

    # ---- what the shop reads -------------------------------------------------

    def shelf_link(self, key, n):
        """A homepage shelf's link words as the pages print them: home.json's label, {n} the count."""
        return self.b.content("home")["shelves"][key]["link_label"].replace("{n}", str(n))

    def test_list_counts_products(self):
        st, d = self.b.api("GET", "collections")
        self.assertEqual(st, 200, d)
        self.assertEqual([i["key"] for i in d["items"]], KEYS)
        products = self.b.content("products")
        for it in d["items"]:
            key = it["key"]
            rows = [p for p in products.values() if key == "all" or p["category"] == key]
            live = len([p for p in rows if p.get("published", True)])
            self.assertEqual((it["published"], it["drafts"]), (live, len(rows) - live), key)
        attars = d["items"][0]
        self.assertEqual(attars["shelf_shows"], {"cards": 5, "link": self.shelf_link("house_ouds", attars["published"])})
        self.assertIsNone(d["items"][-1]["shelf_shows"])
        self.assertIsNone(d["items"][-1]["data"]["circle"])

    def test_catalogue_and_pages_carry_category_text(self):
        copy_doc = self.b.content("copy")
        cats = global_in(self.flow, "BGS_CATS")
        self.assertEqual(list(cats), KEYS)
        for key in KEYS:
            want = dict(copy_doc["categories"][key], intro=copy_doc["collection_intros"][key])
            self.assertEqual(cats[key], want, key)
        for pid, doc in global_in(self.flow, "BGS_CATALOGUE").items():
            self.assertEqual(doc["crumb"], cats[doc["cat"]]["crumb"], pid)
        col = self.page("collection.html")
        self.assertIn("<span class=\"eyebrow\" data-crumb>Home / All products</span>", col)
        self.assertIn(">%s</h2>" % cats["all"]["label"], col)
        self.assertIn("data-intro>%s</p>" % html.escape(cats["all"]["intro"]), col)
        for key in KEYS[:-1]:
            self.assertIn('value="%s">%s</label>' % (key, cats[key]["label"]), col)
        shop = (self.flow / "assets" / "shop.js").read_text(encoding="utf-8")
        for gone in ("CAT_LABEL", "CAT_INTRO", "oud oils, Reserve", "EDP sprays"):
            self.assertNotIn(gone, shop)

    def test_home_headings_and_links_come_from_content(self):
        home_doc = self.b.content("home")
        home = self.page("index.html")
        sec = home_doc["sections"]
        n = {c: len(self.published(c)) for c in ("attars", "edp")}
        link = lambda key, count=0: html.escape(self.shelf_link(key, count))
        self.assertIn('<h2>%s</h2><a href="collection.html?cat=attars">%s &rarr;</a>' % (sec["house_ouds"], link("house_ouds", n["attars"])), home)
        self.assertIn('<h2>%s</h2><a href="collection.html?cat=attars">%s &rarr;</a>' % (sec["reserve"], link("reserve")), home)
        self.assertIn('<h2>%s</h2><a href="collection.html?cat=gift-sets">%s &rarr;</a>' % (sec["gift_sets"], link("gift_sets")), home)
        self.assertIn('<h2>%s</h2></div>' % sec["scent_family"], home)
        self.assertIn('<h2>%s</h2><a href="collection.html?cat=bakhoor">%s &rarr;</a>' % (html.escape(sec["bakhoor"]), link("bakhoor")), home)
        self.assertIn('<h2>%s</h2><a href="collection.html?cat=edp">%s &rarr;</a>' % (sec["edp"], link("edp", n["edp"])), home)
        self.assertEqual(shelf_html(home, "attars").count("data-add="), 5)
        self.assertEqual(shelf_html(home, "bakhoor").count("data-add="), len(self.published("bakhoor")))

    def test_schema_marks_the_wired_fields(self):
        st, s = self.b.api("GET", "schema")
        self.assertEqual(st, 200)
        c = {f["path"]: f for f in s["resources"]["copy"]["fields"]}
        hm = {f["path"]: f for f in s["resources"]["home"]["fields"]}
        for key in KEYS:
            for p in ("/categories/%s/label" % key, "/categories/%s/crumb" % key, "/collection_intros/%s" % key):
                self.assertNotEqual(c[p].get("rendered"), False, p)
        for sid in ("house_ouds", "reserve", "gift_sets", "bakhoor", "edp"):
            self.assertNotEqual(hm["/sections/" + sid].get("rendered"), False, sid)
            self.assertTrue(hm["/shelves/%s/limit" % sid]["nullable"], sid)
        self.assertNotEqual(hm["/sections/scent_family"].get("rendered"), False)
        self.assertIs(hm["/sections/delivered_today"]["rendered"], False)

    # ---- one save, three documents -------------------------------------------

    def test_one_save_writes_copy_home_and_navigation(self):
        before = self.one("attars")["data"]
        n = len(self.published("attars"))

        def change(d):
            d.update(label="Attar oils", crumb="Oils", intro="Oils in 3 ml and 6 ml.")
            d["circle"]["label"] = "Oils and attars"
            d["shelf"].update(heading="House attars", limit=3, link_label="See all {n}")
        st, res = self.put("attars", change)
        try:
            self.assertEqual(st, 200, res)
            self.assertEqual(res["changed"], ["copy", "home", "navigation"])
            self.assertTrue(res["build"]["ok"])
            self.assertEqual(res["rev"], self.one("attars")["rev"])
            home = self.page("index.html")
            self.assertIn('<h2>House attars</h2><a href="collection.html?cat=attars">See all %d &rarr;</a>' % n, home)
            self.assertEqual(shelf_html(home, "attars").count("data-add="), 3)
            self.assertIn("<span>Oils and attars</span>", home)
            self.assertIn('value="attars">Attar oils</label>', self.page("collection.html"))
            self.assertEqual(global_in(self.flow, "BGS_CATS")["attars"],
                             {"label": "Attar oils", "crumb": "Oils", "intro": "Oils in 3 ml and 6 ml."})
            crumbs = {d["crumb"] for d in global_in(self.flow, "BGS_CATALOGUE").values() if d["cat"] == "attars"}
            self.assertEqual(crumbs, {"Oils"})
            self.assertEqual(self.b.content("home")["shelves"]["house_ouds"], {"limit": 3, "link_label": "See all {n}"})
            nav = self.b.content("navigation")["categories"]
            self.assertEqual([c["label"] for c in nav if c["href"] == "collection.html?cat=attars"], ["Oils and attars"])
        finally:
            self.restore("attars", before)
        self.assertIn('<a href="collection.html?cat=attars">%s &rarr;</a>' % html.escape(self.shelf_link("house_ouds", n)), self.page("index.html"))

    def test_no_limit_shows_every_product(self):
        before = self.one("attars")["data"]
        st, res = self.put("attars", lambda d: d["shelf"].update(limit=None))
        try:
            self.assertEqual(st, 200, res)
            self.assertEqual(shelf_html(self.page("index.html"), "attars").count("data-add="), len(self.published("attars")))
        finally:
            self.restore("attars", before)

    def test_link_count_follows_published_products(self):
        n = len(self.published("attars"))
        pid = self.published("attars")[0]
        st, p = self.b.api("GET", "products/" + pid)
        self.assertEqual(st, 200, p)
        st, res = self.b.api("PUT", "products/" + pid, {"data": dict(p["data"], published=False)}, rev=p["rev"])
        self.assertEqual(st, 200, res)
        try:
            self.assertIn('<a href="collection.html?cat=attars">%s &rarr;</a>' % html.escape(self.shelf_link("house_ouds", n - 1)), self.page("index.html"))
            item = [i for i in self.b.api("GET", "collections")[1]["items"] if i["key"] == "attars"][0]
            self.assertEqual((item["published"], item["shelf_shows"]["link"]), (n - 1, self.shelf_link("house_ouds", n - 1)))
        finally:
            st, cur = self.b.api("GET", "products/" + pid)
            st, res = self.b.api("PUT", "products/" + pid, {"data": p["data"]}, rev=cur["rev"])
            self.assertEqual(st, 200, res)
        self.assertIn("%s &rarr;" % html.escape(self.shelf_link("house_ouds", n)), self.page("index.html"))

    def test_reorder_moves_the_shelf(self):
        st, lst = self.b.api("GET", "products?category=attars")
        ids = [i["id"] for i in lst["items"]]
        live = set(self.published("attars"))
        last = [i for i in ids if i in live][-1]
        body = {"category": "attars", "ids": [last] + [i for i in ids if i != last], "expect_collection_rev": lst["collection_rev"]}
        st, res = self.b.api("POST", "products/reorder", body)
        self.assertEqual(st, 200, res)
        try:
            first = re.search(r'href="product\.html\?p=([a-z0-9-]+)"', shelf_html(self.page("index.html"), "attars"))
            self.assertEqual(first.group(1), last)
        finally:
            st, cur = self.b.api("GET", "products?category=attars")
            st, res = self.b.api("POST", "products/reorder", {"category": "attars", "ids": ids, "expect_collection_rev": cur["collection_rev"]})
            self.assertEqual(st, 200, res)

    def test_all_products_page_text(self):
        before = self.one("all")["data"]
        st, res = self.put("all", lambda d: d.update(label="Everything", crumb="Shop", intro="All of it, in one place."))
        try:
            self.assertEqual(st, 200, res)
            self.assertEqual(res["changed"], ["copy"])
            col = self.page("collection.html")
            self.assertIn("data-crumb>Home / Shop</span>", col)
            self.assertIn("data-title>Everything</h2>", col)
            self.assertIn("data-intro>All of it, in one place.</p>", col)
            self.assertEqual(global_in(self.flow, "BGS_CATS")["all"]["label"], "Everything")
        finally:
            self.restore("all", before)

    def test_other_edits_leave_a_collection_current(self):
        d = self.one("gift-sets")
        st, doc = self.b.api("GET", "documents/copy")
        before = copy.deepcopy(doc["data"])
        doc["data"]["quiz_banner"]["eyebrow"] = "Five questions"
        st, res = self.b.api("PUT", "documents/copy", {"data": doc["data"]}, rev=doc["rev"])
        self.assertEqual(st, 200, res)
        try:
            self.assertEqual(self.one("gift-sets")["rev"], d["rev"])
            st, res = self.b.api("PUT", "collections/gift-sets", {"data": dict(d["data"], intro="Sets, wrapped.")}, rev=d["rev"])
            self.assertEqual(st, 200, res)
            self.assertEqual(self.b.content("copy")["quiz_banner"]["eyebrow"], "Five questions")
            self.assertEqual(global_in(self.flow, "BGS_CATS")["gift-sets"]["intro"], "Sets, wrapped.")
        finally:
            st, cur = self.b.api("GET", "documents/copy")
            st, res = self.b.api("PUT", "documents/copy", {"data": before}, rev=cur["rev"])
            self.assertEqual(st, 200, res)

    # ---- what the view refuses -----------------------------------------------

    def test_saves_need_the_current_rev(self):
        d = self.one("edp")
        st, res = self.b.api("PUT", "collections/edp", {"data": d["data"]})
        self.assertEqual((st, res["error"]["code"]), (428, "rev_required"))
        st, res = self.b.api("PUT", "collections/edp", {"data": d["data"]}, rev="0" * 16)
        self.assertEqual((st, res["error"]["code"]), (412, "stale_rev"))
        self.assertEqual(res["error"]["details"], {"current_rev": d["rev"], "current": d["data"]})

    def test_refuses_what_the_view_does_not_own(self):
        for key, change, path in (
                ("attars", lambda d: d.update(key="reserve"), "/key"),
                ("all", lambda d: d.update(circle={"label": "Everything"}), "/circle"),
                ("all", lambda d: d.update(shelf={"heading": "All"}), "/shelf")):
            st, res = self.put(key, change)
            self.assertEqual((st, res["error"]["code"]), (403, "not_editable"), (key, path, res))
            self.assertEqual(res["error"]["details"]["path"], path)
        # The circle's picture is filled by uploads (Navigation and Files), so
        # a save through the view may only point it at a picture that is there.
        for image, code in (("assets/cat/no-such-circle.png", "missing_file"), ("circle.txt", "format")):
            st, res = self.put("attars", lambda d: d["circle"].update(image=image))
            self.assertEqual((st, res["error"]["code"]), (422, "validation"), res)
            self.assertEqual([(e["path"], e["code"], e["document"]) for e in res["error"]["details"]],
                             [("/circle/image", code, "navigation")])
        self.assertEqual(self.b.content("navigation")["categories"][0]["image"], "assets/cat/attars.png")

    def test_bad_values_land_on_the_view(self):
        for change, path, code in (
                (lambda d: d.update(label=""), "/label", "required"),
                (lambda d: d.update(intro="Oils <b>bold</b>"), "/intro", "markup"),
                (lambda d: d.update(crumb="Oils" + chr(0x2014) + "attars"), "/crumb", "em_dash"),
                (lambda d: d["shelf"].update(link_label="All {x}"), "/shelf/link_label", "format"),
                (lambda d: d["shelf"].update(limit=0), "/shelf/limit", "too_small"),
                (lambda d: d["shelf"].update(limit=21), "/shelf/limit", "too_big"),
                (lambda d: d["circle"].update(tint="neon"), "/circle/tint", "choice")):
            st, res = self.put("bakhoor", change)
            self.assertEqual((st, res["error"]["code"]), (422, "validation"), (path, res))
            self.assertIn((path, code), [(e["path"], e["code"]) for e in res["error"]["details"]])

    def test_a_link_to_a_product_that_does_not_exist_is_refused(self):
        # a link that names a product with p= must name one that exists, as a
        # product-ref field must: here a footer link and a banner button
        for doc, change, path in (
                ("navigation", lambda d: d["footer"][1]["links"][0].update(href="product.html?p=ghost&tab=delivery"),
                 "/footer/1/links/0/href"),
                ("home", lambda d: d["hero_slides"][1]["primary"].update(href="product.html?p=ghost"),
                 "/hero_slides/1/primary/href")):
            st, d = self.b.api("GET", "documents/" + doc)
            self.assertEqual(st, 200, d)
            data = copy.deepcopy(d["data"])
            change(data)
            st, res = self.b.api("PUT", "documents/" + doc, {"data": data}, rev=d["rev"])
            self.assertEqual((st, res["error"]["code"]), (422, "validation"), (doc, res))
            self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [(path, "unknown_product")])
            self.assertEqual(self.b.content(doc), d["data"])

    def test_unknown_collection_is_not_found(self):
        self.assertEqual(self.b.api("GET", "collections/reserve")[0], 404)
        self.assertEqual(self.b.api("PUT", "collections/reserve", {"data": {}}, rev="x")[0], 404)

    def test_unreadable_content_stops_the_build(self):
        for name, change, says in (
                ("home", lambda d: d["shelves"]["edp"].update(limit="5"), "home.json shelves.edp.limit"),
                ("home", lambda d: d["sections"].update(edp=""), "home.json sections.edp"),
                ("copy", lambda d: d["categories"]["edp"].update(label=""), "copy.json categories.edp.label")):
            tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgscoll-"))
            try:
                flow = tmp / "flow"
                shutil.copytree(str(self.flow / "content"), str(flow / "content"))
                for f in ("build.py", "edp_data.json"):
                    shutil.copy2(str(self.flow / f), str(flow / f))
                path = flow / "content" / (name + ".json")
                doc = json.loads(path.read_text(encoding="utf-8"))
                change(doc)
                path.write_text(json.dumps(doc), encoding="utf-8")
                p = subprocess.run([sys.executable, "build.py"], cwd=str(flow), capture_output=True, text=True, timeout=60)
                self.assertNotEqual(p.returncode, 0, says)
                self.assertIn(says, p.stderr)
            finally:
                shutil.rmtree(str(tmp), ignore_errors=True)


@unittest.skipUnless(os.path.exists(dom_diff.CHROME), "headless Chrome is not installed")
class DrivenReorder(unittest.TestCase):
    """A collection's Move buttons driven in headless Chrome."""

    def setUp(self):
        self.b = Box(PORT)
        self.c = cdp_pipe.Chrome()

    def tearDown(self):
        self.c.close()
        self.b.close()

    def order(self, cat):
        st, lst = self.b.api("GET", "products?category=" + cat)
        self.assertEqual(st, 200, lst)
        return [i["id"] for i in lst["items"]]

    def test_a_double_click_on_move_saves_once_without_a_false_error(self):
        cat = "bakhoor"
        before = self.order(cat)
        self.c.go("http://localhost:%d/admin/#/collections/%s" % (self.b.port, cat))
        self.c.wait("!!document.querySelector('[data-move$=\\':down\\']')", 25)
        # Two clicks in one turn: the second runs while the first reorder is
        # still in flight. Without the guard it sends the pre-reload list, is
        # refused, and shows "The order was not saved".
        self.c.js("(() => { const b = document.querySelector('[data-move$=\":down\"]'); b.click(); b.click(); })()")
        self.c.wait("[...document.querySelectorAll('.toast')].some(e => e.textContent.includes('Order saved'))", 25)
        self.c.js("new Promise(r => setTimeout(r, 400))")
        self.assertFalse(self.c.js("document.body.textContent.includes('The order was not saved')"),
                         "a false 'not saved' banner appeared")
        # the first product moved down exactly one place, no more
        self.assertEqual(self.order(cat), [before[1], before[0]] + before[2:])
        self.assertEqual(self.c.errors(), [], "the page threw or logged an error")


if __name__ == "__main__":
    unittest.main()
