"""The admin server end to end, against a temporary clone of the repository.

    /usr/bin/python3 -m unittest discover -s admin/tests        # from the repo root

Every test that writes does so in the clone, on a spare port, with --no-push.
"""
import json
import os
import unittest

from box import Box

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

    def test_readonly_unknown_and_guarded_fields(self):
        b = self.b
        d = self._product("vibe")
        self.assertEqual(b.api("PUT", "products/vibe", {"data": dict(d["data"], images=[])}, rev=d["rev"])[0], 403)
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


if __name__ == "__main__":
    unittest.main()
