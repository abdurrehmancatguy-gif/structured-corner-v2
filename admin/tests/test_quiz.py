"""The scent quiz document: its rules, and what a save does to quiz.html.

    /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_quiz.py'

The rule checks call validate and service directly; the API tests run
against a temporary clone on port 4752 (ADMIN_QUIZ_PORT), with --no-push,
and read the page and catalogue.js the build wrote there.
"""
import copy
import json
import os
import pathlib
import sys
import unittest

from box import Box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import service, validate  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402
from bgsadmin.schema import quiz as schema  # noqa: E402

PORT = int(os.environ.get("ADMIN_QUIZ_PORT", "4752"))
CONTENT = pathlib.Path(__file__).resolve().parents[2] / "flow" / "content"


def content(name="quiz"):
    return json.loads((CONTENT / ("%s.json" % name)).read_text(encoding="utf-8"))


def problems(data):
    errors, _ = validate.document("quiz", data, schema.FIELDS, {"products": content("products")})
    return sorted((e["path"], e["code"]) for e in errors)


class RuleTests(unittest.TestCase):
    """The quiz's schema on its own, without a server."""

    def test_the_content_keeps_its_own_rules(self):
        self.assertEqual(problems(content()), [])

    def test_facets_are_words_listed_at_most_as_often_as_allowed(self):
        d = content()
        d["answers"][0]["facets"] = ["citrus", "citrus", "citrus", "Rose", "white-floral"]
        d["profiles"][0]["facets"] = ["citrus", "citrus"]
        d["profiles"][1]["facets"] = []
        d["profiles"][2]["product"] = "no-such-spray"
        self.assertEqual(problems(d), [("/answers/0/facets/0", "repeated"), ("/answers/0/facets/3", "format"),
                                       ("/profiles/0/facets/0", "repeated"), ("/profiles/1/facets", "too_few"),
                                       ("/profiles/2/product", "unknown_product")])

    def test_the_step_line_and_score_keep_their_placeholders(self):
        d = content()
        d["page"]["step_label"], d["result"]["score"] = "Question of {total}", "{shared} of {all}"
        self.assertEqual(problems(d), [("/page/step_label", "format"), ("/result/score", "format")])
        d["page"]["step_label"], d["result"]["score"] = "{n} {n}", "{total}: {shared}"
        self.assertEqual(problems(d), [("/page/step_label", "format")])
        d["page"]["step_label"] = "{n}/{total}"
        self.assertEqual(problems(d), [])

    def test_keys_and_kinds_are_fixed_and_the_rest_is_editable(self):
        old = content()
        for change in (lambda d: d["questions"][0]["options"][0].update(key="weekday"),
                       lambda d: d["answers"][0].update(key="weekday"),
                       lambda d: d["questions"][0].update(kind="tone"),
                       lambda d: d["questions"][0]["options"].pop(),
                       lambda d: d["questions"][0]["options"].reverse(),
                       lambda d: d["questions"].pop(),
                       lambda d: d["answers"].append({"key": "new", "facets": [], "label": ""})):
            new = copy.deepcopy(old)
            change(new)
            with self.assertRaises(ApiError) as cm:
                service.enforce(schema.FIELDS, old, new)
            self.assertEqual(cm.exception.status, 403)
        new = copy.deepcopy(old)
        new["questions"][0]["options"][0]["label"] = "Most days"
        new["questions"][2]["columns"] = 1
        new["answers"][0]["facets"] = ["citrus", "violet", "violet"]
        new["profiles"].reverse()
        new["profiles"].pop()
        service.enforce(schema.FIELDS, old, new)


class QuizApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def doc(self):
        st, d = self.b.api("GET", "documents/quiz")
        self.assertEqual(st, 200, d)
        return d

    def page(self):
        return (self.b.repo / "flow" / "quiz.html").read_text(encoding="utf-8")

    def bgs_quiz(self):
        js = (self.b.repo / "flow" / "assets" / "catalogue.js").read_text(encoding="utf-8")
        line = [x for x in js.splitlines() if x.startswith("window.BGS_QUIZ = ")]
        self.assertEqual(len(line), 1)
        return json.loads(line[0][len("window.BGS_QUIZ = "):-1])

    def put(self, data, rev):
        return self.b.api("PUT", "documents/quiz", {"data": data}, rev=rev)

    def test_the_document_is_what_the_page_and_the_shop_read(self):
        d = self.doc()
        self.assertEqual(d["data"], self.b.content("quiz"))
        q = self.bgs_quiz()
        self.assertEqual(q["profiles"], d["data"]["profiles"])
        self.assertEqual(list(q["answers"]), [a["key"] for a in d["data"]["answers"]])
        html = self.page()
        for question in d["data"]["questions"]:
            self.assertIn("<h2>%s</h2>" % question["title"], html)
            for o in question["options"]:
                self.assertIn('data-a="%s"' % o["key"], html)
        self.assertNotIn("AED 89", html)
        st, s = self.b.api("GET", "schema")
        self.assertEqual(s["resources"]["quiz"]["resource"]["label"], "Scent quiz")
        st, s = self.b.api("GET", "status")
        self.assertIn("quiz", s["revs"])

    def test_an_edited_question_reaches_the_page(self):
        d = self.doc()
        data = copy.deepcopy(d["data"])
        data["questions"][1]["title"] = "How should it feel on you?"
        data["questions"][1]["options"][0]["label"] = "Loud & proud"
        data["page"]["step_label"] = "Step {n} of {total}"
        st, res = self.put(data, d["rev"])
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        html = self.page()
        self.assertIn("<h2>How should it feel on you?</h2>", html)
        self.assertIn('data-a="bold">Loud &amp; proud<span>', html)
        self.assertIn("Step <b data-qnum>1</b> of %d" % len(data["questions"]), html)
        st, res = self.put(d["data"], res["rev"])
        self.assertEqual(st, 200, res)
        self.assertIn("<h2>%s</h2>" % d["data"]["questions"][1]["title"], self.page())

    def test_an_unknown_product_is_refused_and_nothing_changes(self):
        d = self.doc()
        before = self.page()
        data = copy.deepcopy(d["data"])
        data["profiles"][0]["product"] = "no-such-spray"
        st, res = self.put(data, d["rev"])
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]],
                         [("/profiles/0/product", "unknown_product")])
        self.assertEqual(self.b.content("quiz"), d["data"])
        self.assertEqual(self.page(), before)

    def test_option_keys_cannot_change(self):
        d = self.doc()
        for path, change in (("/questions/0/options/0/key", lambda x: x["questions"][0]["options"][0].update(key="weekday")),
                             ("/answers/0/key", lambda x: x["answers"][0].update(key="weekday"))):
            data = copy.deepcopy(d["data"])
            change(data)
            st, res = self.put(data, d["rev"])
            self.assertEqual((st, res["error"]["code"]), (403, "not_editable"))
            self.assertEqual(res["error"]["details"]["path"], path)
        self.assertEqual(self.b.content("quiz"), d["data"])

    def test_a_product_the_quiz_names_cannot_be_deleted(self):
        pid = self.doc()["data"]["profiles"][0]["product"]
        st, p = self.b.api("GET", "products/" + pid)
        self.assertIn({"where": "Scent quiz, profile 1", "link": "#/content/quiz"}, p["refs"])
        st, res = self.b.api("DELETE", "products/" + pid, rev=p["rev"])
        self.assertEqual((st, res["error"]["code"]), (409, "referenced"))


if __name__ == "__main__":
    unittest.main()
