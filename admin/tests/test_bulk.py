"""Bulk saves and the product CSV, end to end, against a temporary clone.

    /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_bulk.py'

Every test puts back what it changed, so they can run in any order.
"""
import csv
import io
import os
import pathlib
import sys
import unittest

from box import Box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import csvio  # noqa: E402

PORT = int(os.environ.get("ADMIN_BULK_PORT", "4771"))


def table(text):
    """A CSV file's header and its rows as dicts, as a spreadsheet shows them."""
    rows = list(csv.reader(io.StringIO(text.lstrip(csvio.BOM), newline="")))
    return rows[0], [dict(zip(rows[0], r)) for r in rows[1:]]


def to_csv(header, rows):
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for r in rows:
        w.writerow([r.get(h, "") for h in header])
    return buf.getvalue()


class GuardTests(unittest.TestCase):
    def test_the_guard_round_trips_exactly(self):
        for s in ("=1+2", "+1", "-5", "@x", chr(9) + "x", chr(13) + "x", "'Tis", "'=x", "'", "plain", ""):
            self.assertEqual(csvio.unguard(csvio.guard(s)), s, s)
        self.assertEqual(csvio.guard("=HYPERLINK(1)"), "'=HYPERLINK(1)")
        self.assertEqual(csvio.unguard("'plain"), "'plain")


class BulkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def product(self, pid):
        st, d = self.b.api("GET", "products/" + pid)
        self.assertEqual(st, 200, d)
        return d["rev"], d["data"]

    def bulk(self, changes, confirm=None):
        body = {"changes": [{"id": pid, "rev": rev, "data": data} for pid, rev, data in changes]}
        if confirm:
            body["confirm_guarded"] = confirm
        return self.b.api("POST", "products/bulk", body)

    def export(self, ids=None):
        path = "/admin/api/v1/products/export.csv" + ("?ids=" + ",".join(ids) if ids else "")
        return self.b.raw("GET", path, headers={"X-Admin-Token": self.b.token})

    def rows_of(self, ids):
        st, _, body = self.export(ids)
        self.assertEqual(st, 200, body)
        return table(body.decode("utf-8"))

    def check(self, text):
        st, res = self.b.api("POST", "products/import", {"csv": text, "mode": "dry-run"})
        self.assertEqual(st, 200, res)
        return res

    def apply(self, plan_id, confirm=None):
        body = {"plan_id": plan_id, "mode": "apply"}
        if confirm:
            body["confirm_guarded"] = confirm
        return self.b.api("POST", "products/import", body)

    # ---- bulk ------------------------------------------------------------------

    def test_bulk_save_is_all_or_nothing(self):
        (r1, d1), (r2, d2) = self.product("be-mine"), self.product("vibe")
        st, res = self.bulk([("be-mine", r1, dict(d1, price=90)), ("vibe", r2, dict(d2, price=0, order=999))])
        self.assertEqual(st, 422, res)
        errors = res["error"]["details"]["errors"]
        self.assertEqual(sorted(errors), ["vibe"])
        self.assertEqual({e["code"] for e in errors["vibe"]}, {"not_editable", "too_small"})
        self.assertEqual(self.b.content("products")["be-mine"]["price"], d1["price"])
        st, res = self.bulk([("be-mine", r1, dict(d1, price=90)), ("vibe", r2, dict(d2, price=91))])
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        saved = self.b.content("products")
        self.assertEqual((saved["be-mine"]["price"], saved["vibe"]["price"]), (90, 91))
        self.assertEqual(res["revs"], {"be-mine": self.product("be-mine")[0], "vibe": self.product("vibe")[0]})
        st, res = self.bulk([("be-mine", res["revs"]["be-mine"], d1), ("vibe", res["revs"]["vibe"], d2)])
        self.assertEqual(st, 200, res)

    def test_a_stale_rev_names_the_conflicting_products(self):
        (ra, da), (rb, db) = self.product("amore"), self.product("bakhoor-1")
        st, res = self.b.api("PUT", "products/amore", {"data": dict(da, stock=7)}, rev=ra)
        self.assertEqual(st, 200, res)
        st, out = self.bulk([("amore", ra, dict(da, stock=8)), ("bakhoor-1", rb, dict(db, stock=9)),
                             ("no-such-product", "0", {})])
        self.assertEqual(st, 412, out)
        self.assertEqual(out["error"]["details"]["conflicts"],
                         [{"id": "amore", "current_rev": res["rev"]}, {"id": "no-such-product", "current_rev": None}])
        self.assertEqual(self.b.content("products")["bakhoor-1"].get("stock"), db.get("stock"))
        self.assertEqual(self.b.api("PUT", "products/amore", {"data": da}, rev=res["rev"])[0], 200)

    def test_never_discounted_needs_confirming_per_product(self):
        rev, d = self.product("discovery-trio")
        self.assertFalse(d["never_discount"])
        change = [("discovery-trio", rev, dict(d, never_discount=True))]
        st, res = self.bulk(change)
        self.assertEqual(st, 428, res)
        self.assertEqual(res["error"]["details"]["guarded"], {"discovery-trio": ["never_discount"]})
        self.assertEqual(self.bulk(change, {"vibe": ["never_discount"]})[0], 428)
        self.assertFalse(self.b.content("products")["discovery-trio"]["never_discount"])
        st, res = self.bulk(change, {"discovery-trio": ["never_discount"]})
        self.assertEqual(st, 200, res)
        self.assertTrue(self.b.content("products")["discovery-trio"]["never_discount"])
        st, _ = self.bulk([("discovery-trio", res["revs"]["discovery-trio"], d)], {"discovery-trio": ["never_discount"]})
        self.assertEqual(st, 200)

    # ---- CSV -------------------------------------------------------------------

    def test_export_then_import_plans_every_row_unchanged(self):
        st, hd, body = self.export()
        self.assertEqual(st, 200, body)
        self.assertEqual(hd.get("Content-Type"), "text/csv; charset=utf-8")
        self.assertEqual(hd.get("Content-Disposition"), 'attachment; filename="bgs-products.csv"')
        self.assertTrue(body.startswith(csvio.BOM.encode("utf-8") + b"Handle,Title,Status,Category,Price,Default size,"))
        text = body.decode("utf-8")
        header, rows = table(text)
        self.assertEqual(header, csvio.HEADERS)
        self.assertEqual(sorted(r["Handle"] for r in rows), sorted(self.b.content("products")))
        res = self.check(text)
        self.assertEqual({r["action"] for r in res["rows"]}, {"unchanged"})
        self.assertEqual(res["counts"]["unchanged"], len(rows))
        self.assertEqual([r["Handle"] for r in self.rows_of(["vibe", "be-mine"])[1]], ["be-mine", "vibe"])
        self.assertEqual(self.export(["no-such-product"])[0], 404)

    def test_a_checked_file_applies_once_and_only_while_current(self):
        header, rows = self.rows_of(["imperial-crown"])
        was = dict(rows[0])
        rows[0].update({"Price": "80", "Size 2 price": "80"})
        res = self.check(to_csv(header, rows))
        row = res["rows"][0]
        self.assertEqual((row["line"], row["id"], row["action"]), (2, "imperial-crown", "update"))
        self.assertEqual(row["changes"], [{"field": "Price", "before": was["Price"], "after": "80"},
                                          {"field": "Size 2 price", "before": was["Size 2 price"], "after": "80"}])
        st, out = self.apply(res["plan_id"])
        self.assertEqual(st, 200, out)
        self.assertEqual(out["updated"], ["imperial-crown"])
        self.assertEqual(out["revs"]["imperial-crown"], self.product("imperial-crown")[0])
        saved = self.b.content("products")["imperial-crown"]
        self.assertEqual((saved["price"], saved["sizes"][1]["price"]), (80, 80))
        self.assertEqual(self.apply(res["plan_id"])[0], 404)
        # a product saved after the check stops the check from applying
        back = self.check(to_csv(header, [was]))
        rev, d = self.product("bakhoor-1")
        st, res = self.bulk([("bakhoor-1", rev, dict(d, stock=3))])
        self.assertEqual(st, 200, res)
        st, out = self.apply(back["plan_id"])
        self.assertEqual(st, 412, out)
        self.assertEqual(self.b.content("products")["imperial-crown"]["price"], 80)
        self.assertEqual(self.bulk([("bakhoor-1", res["revs"]["bakhoor-1"], d)])[0], 200)
        st, out = self.apply(self.check(to_csv(header, [was]))["plan_id"])
        self.assertEqual(st, 200, out)
        self.assertEqual(self.b.content("products")["imperial-crown"]["price"], int(was["Price"]))

    def test_a_never_discounted_change_in_a_file_needs_its_own_confirmation(self):
        header, rows = self.rows_of(["bakhoor-1"])
        self.assertEqual(rows[0]["Never discounted"], "FALSE")
        rows[0]["Never discounted"] = "TRUE"
        res = self.check(to_csv(header, rows))
        self.assertEqual(res["rows"][0]["confirm"], ["never_discount"])
        self.assertEqual(res["needs_confirm"], {"bakhoor-1": ["never_discount"]})
        st, out = self.apply(res["plan_id"])
        self.assertEqual(st, 428, out)
        self.assertEqual(out["error"]["details"]["guarded"], {"bakhoor-1": ["never_discount"]})
        st, out = self.apply(res["plan_id"], {"bakhoor-1": ["never_discount"]})
        self.assertEqual(st, 200, out)
        self.assertTrue(self.b.content("products")["bakhoor-1"]["never_discount"])
        rev, d = self.product("bakhoor-1")
        st, _ = self.bulk([("bakhoor-1", rev, dict(d, never_discount=False))], {"bakhoor-1": ["never_discount"]})
        self.assertEqual(st, 200)

    def test_the_formula_guard_works_both_ways(self):
        rev, d = self.product("vibe")
        risky = {"seo_title": "=SUM(1,2)", "seo_description": "+ a second thought", "image_alt": "'Tis a bottle"}
        st, res = self.bulk([("vibe", rev, dict(d, **risky))])
        self.assertEqual(st, 200, res)
        text = self.export(["vibe"])[2].decode("utf-8")
        header, rows = table(text)
        self.assertEqual((rows[0]["SEO title"], rows[0]["SEO description"], rows[0]["Image alt"]),
                         ("'=SUM(1,2)", "'+ a second thought", "''Tis a bottle"))
        self.assertEqual(self.check(text)["rows"][0]["action"], "unchanged")
        rows[0].update({"SEO title": "'@home", "Image alt": "'plain"})
        row = self.check(to_csv(header, rows))["rows"][0]
        self.assertEqual({c["field"]: c["after"] for c in row["changes"]}, {"SEO title": "@home", "Image alt": "'plain"})
        self.assertEqual(self.bulk([("vibe", res["revs"]["vibe"], d)])[0], 200)

    def test_malformed_rows_come_back_as_error_rows_with_their_lines(self):
        text = ("Handle,Title,Price,Category\r\n"
                'vibe,"Vibe\r\nsecond line",85,edp\r\n'      # lines 2 and 3
                "be-mine,Be Mine\r\n"                        # 4
                "amore,Amore,abc,edp\r\n"                    # 5
                ",Nameless,5,edp\r\n"                        # 6
                "csv-new,New,40,perfume\r\n"                 # 7
                "amore,Again,85,edp\r\n"                     # 8
                "\r\n"                                       # 9, blank, skipped
                'csv-late,"never closed,5,edp\r\n'           # 10
                "csv-after,After,5,edp\r\n")
        res = self.check(text)
        got = [(r["line"], r["id"], r["action"]) for r in res["rows"]]
        self.assertEqual(got, [(2, "vibe", "error"), (4, "be-mine", "error"), (5, "amore", "error"), (6, "", "error"),
                               (7, "csv-new", "error"), (8, "amore", "error"), (10, "", "error")])
        found = [{(e["code"], e["column"]) for e in r["errors"]} for r in res["rows"]]
        for i, want in enumerate([("control", "Title"), ("cells", ""), ("format", "Price"), ("required", "Handle"),
                                  ("format", "Category"), ("duplicate", "Handle"), ("unreadable", "")]):
            self.assertIn(want, found[i], res["rows"][i])
        st, out = self.apply(res["plan_id"])
        self.assertEqual((st, out["error"]["code"]), (422, "plan_has_errors"))
        half_pair = "Handle,Title\r\nvibe,V" + chr(0xD800) + "\r\n"
        for bad in ("", "Title,Price\r\nx,1\r\n", "Handle,Price,price\r\nvibe,1,1\r\n", half_pair):
            st, out = self.b.api("POST", "products/import", {"csv": bad, "mode": "dry-run"})
            self.assertEqual((st, out["error"]["code"]), (422, "bad_csv"), bad)

    def test_a_new_row_becomes_a_draft_at_the_end(self):
        before = self.b.content("products")
        header = ["Handle", "Title", "Status", "Category", "Price", "Default size", "Order", "Image 1"]
        rows = [{"Handle": "csv-test-oud", "Title": "CSV test oud", "Status": "active", "Category": "bakhoor",
                 "Price": "45", "Default size": "40 g", "Order": "3"},
                {"Handle": "csv-test-two", "Title": "CSV test two", "Category": "bakhoor", "Price": "45",
                 "Default size": "40 g", "Image 1": "csv-test-two-1.jpg"}]
        new, bad = self.check(to_csv(header, rows))["rows"]
        self.assertEqual(new["action"], "create", new)
        self.assertEqual({w["code"] for w in new["warnings"]}, {"draft", "order"})
        self.assertEqual(bad["action"], "error")
        self.assertIn("photo", {e["code"] for e in bad["errors"]})
        st, out = self.apply(self.check(to_csv(header, rows[:1]))["plan_id"])
        self.assertEqual(st, 200, out)
        self.assertEqual(out["created"], ["csv-test-oud"])
        saved = self.b.content("products")["csv-test-oud"]
        self.assertFalse(saved["published"])
        self.assertEqual(saved["order"], max(d["order"] for d in before.values()) + 1)
        self.assertEqual(list(saved)[:4], ["name", "category", "price", "size"])
        self.assertEqual(saved["images"], [])
        rev, _ = self.product("csv-test-oud")
        self.assertEqual(self.b.api("DELETE", "products/csv-test-oud", rev=rev)[0], 200)


if __name__ == "__main__":
    unittest.main()
