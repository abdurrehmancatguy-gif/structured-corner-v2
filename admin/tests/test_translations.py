"""Translations: the Arabic dictionary document and the dictionary field type.

    /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_translations.py'

The rule checks call validate and service directly; the API tests run
against a temporary clone on port 4751 (ADMIN_TRANSLATIONS_PORT), with
--no-push, and read what the build wrote into catalogue.js.
"""
import json
import os
import pathlib
import sys
import unittest

from box import Box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import service, validate  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402
from bgsadmin.schema import translations as schema  # noqa: E402

PORT = int(os.environ.get("ADMIN_TRANSLATIONS_PORT", "4751"))
DASH = chr(0x2014)


def problems(data):
    errors, _ = validate.document("translations", data, schema.FIELDS, {})
    return [(e["path"], e["code"], e.get("part")) for e in errors]


class RuleTests(unittest.TestCase):
    """The dictionary type on its own, without a server."""

    def test_a_clean_dictionary_passes(self):
        self.assertEqual(problems({"ar": {"Bag": "x", "Summary": "", "Oud / Bakhoor": "y", "a~b": "z"}}), [])

    def test_keys_must_be_the_exact_text(self):
        got = problems({"ar": {"": "x", "Bag ": "x", "<b>Bag</b>": "x", "Tab\there": "x",
                               "k" * 121: "x", "Bag" + DASH: "x", "k" * 120: "x"}})
        self.assertEqual(sorted(got), sorted([
            ("/ar/", "required", "key"), ("/ar/Bag ", "spaces", "key"), ("/ar/<b>Bag<~1b>", "markup", "key"),
            ("/ar/Tab\there", "control", "key"), ("/ar/" + "k" * 121, "too_long", "key"),
            ("/ar/Bag" + DASH, "em_dash", "key")]))

    def test_values_are_text_within_bounds(self):
        got = problems({"ar": {"A": 5, "B": "x" * 301, "C": "50%% off", "D": "a" + DASH + "b", "E": "x" * 300, "F": "line\nbreak"}})
        self.assertEqual(sorted(got), [("/ar/A", "type", "value"), ("/ar/B", "too_long", "value"),
                                       ("/ar/C", "percent", "value"), ("/ar/D", "em_dash", "value"),
                                       ("/ar/F", "control", "value")])

    def test_shape_and_size(self):
        self.assertEqual(problems({}), [("/ar", "required", None)])
        self.assertEqual(problems({"ar": {}}), [])
        self.assertEqual(problems({"ar": ["Bag"]}), [("/ar", "type", None)])
        self.assertEqual(problems({"ar": {"k%d" % i: "" for i in range(401)}}), [("/ar", "too_many", None)])
        self.assertEqual(problems({"ar": {"k%d" % i: "" for i in range(400)}}), [])

    def test_every_entry_belongs_to_the_dictionary(self):
        f = schema.FIELDS[0]
        for ptr in ("/ar", "/ar/Bag", "/ar/Oud ~1 Bakhoor", "/ar/", "/ar/Bag/deeper"):
            self.assertIs(service.field_for(schema.FIELDS, ptr)[0], f, ptr)
        self.assertEqual(service.field_for(schema.FIELDS, "/fr/Bag"), (None, []))
        old = {"ar": {"Bag": "x"}}
        service.enforce(schema.FIELDS, old, {"ar": {"Bag": "y", "Oud / Bakhoor": "z", "a~b": ""}})
        service.enforce(schema.FIELDS, old, {"ar": {}})
        with self.assertRaises(ApiError) as cm:
            service.enforce(schema.FIELDS, old, dict(old, fr={"Bag": "Sac"}))
        self.assertEqual(cm.exception.status, 403)


class TranslationsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def doc(self):
        st, d = self.b.api("GET", "documents/translations")
        self.assertEqual(st, 200, d)
        return d

    def bgs_ar(self):
        js = (self.b.repo / "flow" / "assets" / "catalogue.js").read_text(encoding="utf-8")
        line = [x for x in js.splitlines() if x.startswith("window.BGS_AR = ")]
        self.assertEqual(len(line), 1)
        return json.loads(line[0][len("window.BGS_AR = "):-1])

    def test_the_document_is_what_the_shop_reads(self):
        d = self.doc()
        self.assertEqual(d["data"], self.b.content("translations"))
        self.assertEqual(self.bgs_ar(), d["data"]["ar"])
        self.assertIn("Add to bag", d["data"]["ar"])
        shop = (self.b.repo / "flow" / "assets" / "shop.js").read_text(encoding="utf-8")
        self.assertIn("window.BGS_AR", shop)
        for en, ar in d["data"]["ar"].items():
            self.assertNotIn('"%s"' % ar, shop, en)
        st, s = self.b.api("GET", "schema")
        self.assertEqual(s["resources"]["translations"]["fields"][0]["type"], "dictionary")
        st, s = self.b.api("GET", "status")
        self.assertIn("translations", s["revs"])

    def test_edit_add_rename_and_remove_entries(self):
        b = self.b
        d = self.doc()
        ar = dict(d["data"]["ar"])
        ar["Bag"] = ar["Your bag"]
        del ar["Summary"]
        ar["Oud / Bakhoor"] = ar.pop("Bakhoor")
        ar["Gift wrap"] = ""
        st, res = b.api("PUT", "documents/translations", {"data": {"ar": ar}}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        self.assertEqual(res["data"]["ar"], ar)
        self.assertEqual(b.content("translations")["ar"], ar)
        self.assertEqual(self.bgs_ar(), ar)
        self.assertEqual(list(b.content("translations")["ar"])[:2], list(d["data"]["ar"])[:2])
        # a stale rev is refused with the current version
        st, res2 = b.api("PUT", "documents/translations", {"data": d["data"]}, rev=d["rev"])
        self.assertEqual(st, 412)
        self.assertEqual(res2["error"]["details"]["current_rev"], res["rev"])
        st, res3 = b.api("PUT", "documents/translations", {"data": d["data"]}, rev=res["rev"])
        self.assertEqual(st, 200, res3)
        self.assertEqual(self.bgs_ar(), d["data"]["ar"])

    def test_bad_entries_are_refused_and_nothing_changes(self):
        b = self.b
        d = self.doc()
        cat = b.repo / "flow" / "assets" / "catalogue.js"
        before = cat.read_bytes()
        ar = dict(d["data"]["ar"], **{"Bag ": "x", "Summary": "a" + DASH})
        st, res = b.api("PUT", "documents/translations", {"data": {"ar": ar}}, rev=d["rev"])
        self.assertEqual(st, 422, res)
        got = sorted((e["path"], e["code"], e["part"], e["key"]) for e in res["error"]["details"])
        self.assertEqual(got, [("/ar/Bag ", "spaces", "key", "Bag "), ("/ar/Summary", "em_dash", "value", "Summary")])
        self.assertEqual(b.api("PUT", "documents/translations", {"data": {"ar": ["Bag"]}}, rev=d["rev"])[0], 422)
        st, res = b.api("PUT", "documents/translations", {"data": dict(d["data"], fr={"Bag": "Sac"})}, rev=d["rev"])
        self.assertEqual((st, res["error"]["code"]), (403, "not_editable"))
        self.assertEqual(b.api("PUT", "documents/translations", {"data": d["data"]})[0], 428)
        self.assertEqual(cat.read_bytes(), before)
        self.assertEqual(b.content("translations"), d["data"])


if __name__ == "__main__":
    unittest.main()
