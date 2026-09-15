"""The admin server end to end, against a temporary clone of the repository.

    /usr/bin/python3 -m unittest discover -s admin/tests        # from the repo root

Every test that writes does so in the clone, on a spare port, with --no-push.
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

from box import ADMIN, REPO, Box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "devtools"))
import dom_diff  # noqa: E402

sys.path.insert(0, str(ADMIN))
from bgsadmin import schema, validate  # noqa: E402

PORT = int(os.environ.get("ADMIN_TEST_PORT", "4731"))


class AdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    # ---- storefront and gate --------------------------------------------------

    def test_storefront_serves_published_files_only(self):
        b = self.b
        self.assertEqual(b.raw("GET", "/")[0], 200)
        self.assertEqual(b.raw("GET", "/assets/flow.min.css")[0], 200)
        for p in ("/content/products.json", "/build.py", "/assets/flow.css", "/tools/make_derivatives.py",
                  "/content/.backups/audit.jsonl", "/%2e%2e/admin/server.py", "/assets/../content/products.json",
                  "/assets/cat/SOURCES.txt", "/admin/ui/../bgsadmin/app.py"):
            st, _, body = b.raw("GET", p)
            self.assertEqual(st, 404, p)
        st, _, body = b.raw("GET", "/no-such-page")
        self.assertEqual(st, 404)
        self.assertIn(b"find that page", body)

    def test_range_request(self):
        st, hd, body = self.b.raw("GET", "/robots.txt", headers={"Range": "bytes=0-3"})
        self.assertEqual(st, 206)
        self.assertEqual(len(body), 4)

    def test_wrong_host_is_refused(self):
        self.assertEqual(self.b.raw("GET", "/", host="evil.example:%d" % PORT)[0], 421)
        self.assertEqual(self.b.raw("GET", "/admin/", host="evil.example")[0], 421)

    def test_admin_page_only_for_navigations(self):
        st, hd, _ = self.b.raw("GET", "/admin/", headers={"Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty"})
        self.assertEqual(st, 403)
        st, hd, _ = self.b.raw("GET", "/admin/", headers={"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "iframe"})
        self.assertEqual(st, 403)
        st, hd, _ = self.b.raw("GET", "/admin/", headers={"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "cross-site"})
        self.assertEqual(st, 403)
        st, hd, _ = self.b.raw("GET", "/admin/", headers={"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"})
        self.assertEqual(st, 200)
        self.assertEqual(hd.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertIn("frame-ancestors 'none'", hd.get("Content-Security-Policy", ""))

    def test_api_needs_token_origin_and_json(self):
        b = self.b
        self.assertEqual(b.api("GET", "products", token=False)[0], 401)
        self.assertEqual(b.api("POST", "build", body={}, origin=False)[0], 403)
        self.assertEqual(b.api("POST", "build", body={}, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(b.api("POST", "build", body=b"{}", ctype="text/plain")[0], 415)
        self.assertEqual(b.api("GET", "products", headers={"Sec-Fetch-Site": "cross-site"})[0], 403)
        st, hd, _ = b.raw("OPTIONS", "/admin/api/v1/products", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "PUT"})
        self.assertEqual(st, 405)
        self.assertFalse(any(k.lower().startswith("access-control") for k in hd))
        self.assertEqual(b.api("PUT", "documents/settings", body=b'{"data":{},"data":{}}', rev="x")[0], 400)

    # ---- products ----------------------------------------------------------------

    def _product(self, pid):
        st, d = self.b.api("GET", "products/" + pid)
        self.assertEqual(st, 200)
        return d

    def test_edit_price_rebuilds_the_site(self):
        b = self.b
        d = self._product("be-mine")
        data = dict(d["data"], price=86)
        st, res = b.api("PUT", "products/be-mine", {"data": data}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        cat = (b.repo / "flow" / "assets" / "catalogue.js").read_text()
        self.assertRegex(cat, r'"be-mine": \{"name": "Be Mine", "meta": [^}]*"pn": 86')
        self.assertEqual(b.content("products")["be-mine"]["price"], 86)
        # a stale rev is refused with the current version
        st, res2 = b.api("PUT", "products/be-mine", {"data": dict(data, price=87)}, rev=d["rev"])
        self.assertEqual(st, 412)
        self.assertEqual(res2["error"]["details"]["current_rev"], res["rev"])
        st, _ = b.api("PUT", "products/be-mine", {"data": dict(data, price=85)}, rev=res["rev"])
        self.assertEqual(st, 200)

    def test_rev_is_required(self):
        d = self._product("vibe")
        self.assertEqual(self.b.api("PUT", "products/vibe", {"data": d["data"]})[0], 428)

    def test_validation_and_markup(self):
        b = self.b
        d = self._product("vibe")
        st, res = b.api("PUT", "products/vibe", {"data": dict(d["data"], price=0)}, rev=d["rev"])
        self.assertEqual(st, 422)
        self.assertEqual(res["error"]["details"][0]["path"], "/price")
        st, res = b.api("PUT", "products/vibe", {"data": dict(d["data"], name="<script>x</script>")}, rev=d["rev"])
        self.assertEqual(st, 422)
        st, res = b.api("PUT", "products/vibe", {"data": dict(d["data"], name="Vibe " + chr(0x2014) + " new")}, rev=d["rev"])
        self.assertEqual(st, 422)

    def test_a_name_or_story_that_is_not_text_is_refused(self):
        # validate.product reads the name and the story for claim words: a
        # value that is not text is a type error on its field, not a 500
        b = self.b
        d = self._product("vibe")
        for change, want in (({"name": 5}, [("/name", "type")]), ({"story": [5]}, [("/story/0", "type")]),
                             ({"story": 5}, [("/story", "type")])):
            st, res = b.api("PUT", "products/vibe", {"data": dict(d["data"], **change)}, rev=d["rev"])
            self.assertEqual(st, 422, (change, res))
            self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], want, change)
        st, res = b.api("POST", "products/bulk", {"changes": [{"id": "vibe", "rev": d["rev"], "data": dict(d["data"], name=5)}]})
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]["errors"]["vibe"]], [("/name", "type")])
        self.assertEqual(self._product("vibe")["rev"], d["rev"])

    def test_markup_written_as_entities_is_refused(self):
        # build.py decodes entities when it writes catalogue.js, so text that
        # decodes to < or > is refused like the characters themselves
        b = self.b
        d = self._product("be-mine")
        for bad in ("&lt;img src=x onerror=alert(1)&gt;", "&#60;b&#x3e;x", "&amp;lt;b&amp;gt;", "&ltb&gt"):
            st, res = b.api("PUT", "products/be-mine", {"data": dict(d["data"], story=[bad])}, rev=d["rev"])
            self.assertEqual(st, 422, bad)
            self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/story/0", "markup")], bad)
        self.assertEqual(self._product("be-mine")["rev"], d["rev"])

    def build(self):
        p = subprocess.run([sys.executable, "build.py"], cwd=str(self.b.repo / "flow"), capture_output=True, text=True, timeout=100)
        self.assertEqual(p.returncode, 0, p.stderr)

    @unittest.skipUnless(os.path.exists(dom_diff.CHROME), "headless Chrome is not installed")
    def test_product_page_puts_content_in_as_text(self):
        # Whatever reaches products.json (here written outside the admin, past
        # its checks), the product page shows the story, the declared
        # ingredients and the size labels as text: nothing in them becomes
        # an element or an attribute.
        path = self.b.repo / "flow" / "content" / "products.json"
        original = path.read_bytes()
        products = json.loads(original)
        p = products["imperial-crown"]
        p["story"] = ["<img src=x onerror=document.body.dataset.pwned=1>", "A second line"]
        p["ingredients"] = "<b data-ing>Alcohol denat.</b>"
        p["sizes"][0]["label"] = '3 ml" data-pwn="1'
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="text-only-"))
        try:
            path.write_text(json.dumps(products, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            self.build()
            dom = dom_diff.dump("http://localhost:%d/product.html?p=imperial-crown" % PORT, 1280, tmp)
        finally:
            path.write_bytes(original)
            self.build()
            shutil.rmtree(str(tmp), ignore_errors=True)
        self.assertIn("<span>&lt;img src=x onerror=document.body.dataset.pwned=1&gt;</span><span>A second line</span>", dom)
        self.assertIsNone(re.search(r"<img[^>]*onerror", dom))
        self.assertIn('<p style="margin:8px 0 0">&lt;b data-ing&gt;Alcohol denat.&lt;/b&gt;</p>', dom)
        self.assertNotIn("<b data-ing", dom)
        self.assertIn('data-size="3 ml&quot; data-pwn=&quot;1', dom)
        self.assertIsNone(re.search(r'<button[^>]*\sdata-pwn="', dom))

    def test_half_a_character_pair_is_refused(self):
        # A JSON \ud800 escape decodes to half of a UTF-16 pair, which no
        # content file can be written with: the save answers 422 on the field
        # instead of failing at the write, and nothing changes.
        b = self.b
        half = chr(0xD800)
        d = self._product("vibe")
        bad = dict(d["data"], name="Vibe " + half)
        st, res = b.api("PUT", "products/vibe", {"data": bad}, rev=d["rev"])
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/name", "control")])
        st, res = b.api("POST", "products/bulk", {"changes": [{"id": "vibe", "rev": d["rev"], "data": bad}]})
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]["errors"]["vibe"]], [("/name", "control")])
        self.assertEqual(self._product("vibe")["rev"], d["rev"])
        st, doc = b.api("GET", "documents/translations")
        self.assertEqual(st, 200)
        for entry, part in (({"Shop " + half: "x"}, "key"), ({"Shop now": "x " + half}, "value")):
            ar = dict(doc["data"]["ar"])
            ar.update(entry)
            st, res = b.api("PUT", "documents/translations", {"data": {"ar": ar}}, rev=doc["rev"])
            self.assertEqual(st, 422, res)
            self.assertEqual([(e["code"], e["part"], e["key"]) for e in res["error"]["details"]],
                             [("control", part, next(iter(entry)))])
        self.assertEqual(b.api("GET", "documents/translations")[1]["rev"], doc["rev"])

    def test_readonly_unknown_and_guarded_fields(self):
        b = self.b
        d = self._product("vibe")
        self.assertEqual(b.api("PUT", "products/vibe", {"data": dict(d["data"], order=999)}, rev=d["rev"])[0], 403)
        self.assertEqual(b.api("PUT", "products/vibe", {"data": dict(d["data"], evil="x")}, rev=d["rev"])[0], 403)
        st, res = b.api("PUT", "products/vibe", {"data": dict(d["data"], never_discount=True)}, rev=d["rev"])
        self.assertEqual(st, 428)
        st, res = b.api("PUT", "products/vibe", {"data": dict(d["data"], never_discount=True), "confirm_guarded": ["never_discount"]}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        st, _ = b.api("PUT", "products/vibe", {"data": dict(res["data"], never_discount=False), "confirm_guarded": ["never_discount"]}, rev=res["rev"])
        self.assertEqual(st, 200)

    def test_build_failure_puts_everything_back(self):
        b = self.b
        flow = b.repo / "flow"
        d = self._product("amore")
        copy_ = flow / "assets" / "img" / "amore-1-600.jpg"
        before = {p: p.read_bytes() for p in [flow / "content" / "products.json", flow / "index.html", flow / "assets" / "catalogue.js"]}
        saved = copy_.read_bytes()
        copy_.unlink()
        try:
            st, res = b.api("PUT", "products/amore", {"data": dict(d["data"], price=90)}, rev=d["rev"])
            self.assertEqual(st, 422, res)
            self.assertEqual(res["error"]["code"], "build_failed")
            self.assertTrue(any("amore-1-600" in p for p in res["error"]["details"]["problems"]))
            for p, data in before.items():
                self.assertEqual(p.read_bytes(), data, p)
        finally:
            copy_.write_bytes(saved)

    def test_create_duplicate_delete(self):
        b = self.b
        st, res = b.api("POST", "products", {"id": "test-scent", "data": {"name": "Test scent", "category": "bakhoor", "price": 40, "size": "30 g"}})
        self.assertEqual(st, 201, res)
        self.assertFalse(res["data"]["published"])
        self.assertEqual(b.api("POST", "products", {"id": "test-scent", "data": {"name": "x", "category": "bakhoor", "price": 1, "size": "1 g"}})[0], 422)
        self.assertEqual(b.api("POST", "products", {"id": "constructor", "data": {"name": "x", "category": "bakhoor", "price": 1, "size": "1 g"}})[0], 422)
        st, dup = b.api("POST", "products/test-scent/duplicate", {"new_id": "test-scent-2"})
        self.assertEqual(st, 201, dup)
        for pid in ("test-scent-2", "test-scent"):
            d = self._product(pid)
            self.assertEqual(b.api("DELETE", "products/" + pid, rev=d["rev"])[0], 200)
        self.assertNotIn("test-scent", b.content("products"))

    def test_ids_and_barcodes_are_matched_as_a_whole(self):
        # a line break after an id is not an id, and a barcode is the digits
        # 0 to 9 only (Python's \d also takes an Arabic-Indic two)
        b = self.b
        new = {"name": "Test scent", "category": "bakhoor", "price": 40, "size": "30 g"}
        st, res = b.api("POST", "products", {"id": "vibe-2\n", "data": new})
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/id", "id")])
        st, res = b.api("POST", "products/vibe/duplicate", {"new_id": "vibe-2\n"})
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/new_id", "id")])
        self.assertEqual([p for p in b.content("products") if p.startswith("vibe-2")], [])
        d = self._product("vibe")
        st, res = b.api("PUT", "products/vibe", {"data": dict(d["data"], barcode="629700019773" + chr(0x0662))}, rev=d["rev"])
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/barcode", "format")])
        self.assertEqual(self._product("vibe")["rev"], d["rev"])

    def test_active_and_never_discounted_are_required(self):
        b = self.b
        d = self._product("vibe")
        data = dict(d["data"])
        del data["published"]
        st, res = b.api("PUT", "products/vibe", {"data": data}, rev=d["rev"])
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/published", "required")])
        st, res = b.api("POST", "products/bulk", {"changes": [{"id": "vibe", "rev": d["rev"], "data": data}]})
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]["errors"]["vibe"]], [("/published", "required")])
        data = dict(d["data"])
        del data["never_discount"]
        self.assertEqual(b.api("PUT", "products/vibe", {"data": data}, rev=d["rev"])[0], 428)     # guarded: asked first
        st, res = b.api("PUT", "products/vibe", {"data": data, "confirm_guarded": ["never_discount"]}, rev=d["rev"])
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/never_discount", "required")])
        self.assertEqual(self._product("vibe")["rev"], d["rev"])

    def test_delete_refuses_a_referenced_product(self):
        d = self._product("platinum-musk-oud")      # a homepage banner links to it
        st, res = self.b.api("DELETE", "products/platinum-musk-oud", rev=d["rev"])
        self.assertEqual(st, 409)
        self.assertTrue(res["error"]["details"]["refs"])

    # ---- documents ---------------------------------------------------------------

    def test_locked_payment_settings(self):
        b = self.b
        st, d = b.api("GET", "documents/settings")
        data = json.loads(json.dumps(d["data"]))
        data["payments"]["cod"] = False
        st, res = b.api("PUT", "documents/settings", {"data": data}, rev=d["rev"])
        self.assertEqual(st, 403)
        self.assertEqual(res["error"]["code"], "locked_field")
        data = json.loads(json.dumps(d["data"]))
        del data["payments"]
        self.assertEqual(b.api("PUT", "documents/settings", {"data": data}, rev=d["rev"])[0], 403)

    def test_edit_navigation_and_href_rules(self):
        b = self.b
        st, d = b.api("GET", "documents/navigation")
        data = json.loads(json.dumps(d["data"]))
        data["footer"][0]["links"][0]["href"] = "javascript:alert(1)"
        self.assertEqual(b.api("PUT", "documents/navigation", {"data": data}, rev=d["rev"])[0], 422)
        data["footer"][0]["links"][0]["href"] = "collection.html?cat=attars"
        data["footer"][0]["links"][0]["label"] = "Perfume oils"
        st, res = b.api("PUT", "documents/navigation", {"data": data}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        self.assertIn(">Perfume oils</a>", (b.repo / "flow" / "index.html").read_text())


class ProductRuleTests(unittest.TestCase):
    """validate.product on values of the wrong type, without a server: each
    is a type error on its own field, and nothing fails on one."""

    @classmethod
    def setUpClass(cls):
        cls.products = json.loads((REPO / "flow" / "content" / "products.json").read_text(encoding="utf-8"))
        cls.fields = schema.load()["products"]["fields"]

    def problems(self, pid, change, stored=None):
        products = dict(self.products, **({pid: stored} if stored is not None else {}))
        errors, _ = validate.product(pid, dict(self.products[pid], **change), products, self.fields, {})
        return [(e["path"], e["code"]) for e in errors]

    def test_values_of_the_wrong_type_are_type_errors(self):
        attar = next(p for p, d in self.products.items() if d["category"] == "attars")
        price = self.products[attar]["price"]
        for pid, change, want in (("vibe", {"name": 5}, [("/name", "type")]),
                                  ("vibe", {"story": 5}, [("/story", "type")]),
                                  ("vibe", {"story": [5]}, [("/story/0", "type")]),
                                  ("vibe", {"related": 5}, [("/related", "type")]),
                                  ("vibe", {"related": "vibe"}, [("/related", "type")]),
                                  (attar, {"sizes": [{"label": ["3 ml"], "price": price}]}, [("/sizes/0/label", "type")]),
                                  (attar, {"sizes": [{"label": "3 ml", "price": price}, {"label": "3 ml", "price": 1}]},
                                   [("/sizes", "duplicate")])):
            self.assertEqual(self.problems(pid, change), want, (pid, change))
        # a stored product whose photos are not a list does not stop an edit
        self.assertEqual(self.problems("vibe", {}, stored=dict(self.products["vibe"], images=5)), [])


class UiSourceTests(unittest.TestCase):
    """Rules read from the admin's own source; no server needed."""

    def test_every_badge_variant_has_a_style(self):
        # A badge variant used in a lib or component file needs its rule in
        # admin.css; one used by a screen may also have it in that screen's
        # own sheet (css/<screen>.css).
        ui = pathlib.Path(__file__).resolve().parent.parent / "ui"
        rules = lambda p: set(re.findall(r"\.badge\.([a-z-]+)", p.read_text(encoding="utf-8"))) if p.is_file() else set()
        shared = rules(ui / "admin.css")
        missing = []
        used = set()
        for p in sorted(ui.rglob("*.js")):
            own = rules(ui / "css" / (p.stem + ".css")) if p.parent.name == "screens" else set()
            for m in re.finditer(r'class:\s*"badge((?: [a-z-]+)+)"', p.read_text(encoding="utf-8")):
                for v in m.group(1).split():
                    used.add(v)
                    if v not in shared | own:
                        missing.append("%s: badge %s" % (p.relative_to(ui), v))
        self.assertIn("muted", used)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
