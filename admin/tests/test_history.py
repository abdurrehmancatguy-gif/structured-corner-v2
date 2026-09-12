"""History: every saved version of a product or a document, the semantic
diff between versions, and restoring one as a normal save.

    ADMIN_HISTORY_PORT=4781 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_history.py'

The server tests run on a temporary clone. Backups older than any real save
are written straight into its flow/content/.backups, the way an older admin
left them, to test restoring what the admin itself could not have saved.
"""
import copy
import json
import os
import pathlib
import sys
import unittest

from box import Box

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import diff, gitops, schema  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402

PORT = int(os.environ.get("ADMIN_HISTORY_PORT", "4781"))
CONTENT = pathlib.Path(__file__).resolve().parent.parent.parent / "flow" / "content"


def load(name):
    return json.loads((CONTENT / ("%s.json" % name)).read_text(encoding="utf-8"))


class DiffTests(unittest.TestCase):
    """The sentences, straight from the module, on today's content."""

    @classmethod
    def setUpClass(cls):
        cls.S = schema.load()
        cls.P = load("products")
        cls.ctx = {"products": cls.P}

    def texts(self, entries):
        return [e["text"] for e in entries]

    def test_product_sentences(self):
        pf = self.S["products"]["fields"]
        a = self.P["be-mine"]
        got = self.texts(diff.product("be-mine", pf, a, dict(a, price=a["price"] + 5), self.ctx))
        self.assertEqual(got, ["Be Mine: price AED %d to AED %d" % (a["price"], a["price"] + 5)])
        got = self.texts(diff.product("be-mine", pf, dict(a, published=False), a, self.ctx))
        self.assertEqual(got, ["Draft to active: Be Mine"])
        self.assertEqual(self.texts(diff.product("be-mine", pf, None, a)), ["Added: Be Mine"])
        self.assertEqual(self.texts(diff.product("be-mine", pf, a, None)), ["Removed: Be Mine"])
        got = self.texts(diff.product("be-mine", pf, a, dict(a, images=list(reversed(a["images"])), never_discount=True)))
        self.assertIn("Be Mine: photos reordered", got)
        self.assertIn("Be Mine: never discounted turned on", got)
        # A key only one version has reads as set, removed or cleared.
        bare = {k: v for k, v in a.items() if k != "badge"}
        self.assertEqual(self.texts(diff.product("be-mine", pf, bare, dict(a, badge=""))), ["Be Mine: badge set to empty"])
        self.assertEqual(self.texts(diff.product("be-mine", pf, dict(a, badge="New"), bare)), ['Be Mine: badge removed (was "New")'])
        self.assertEqual(self.texts(diff.product("be-mine", pf, dict(a, stock=4), dict(a, stock=None))), ["Be Mine: stock cleared (was 4)"])

    def test_rows_are_lined_up_by_content(self):
        hf = self.S["home"]["fields"]
        home = load("home")
        b = copy.deepcopy(home)
        b["hero_slides"][1]["headline"] = "Something new"
        self.assertEqual(self.texts(diff.document(hf, home, b)), ["Banner slide 2: headline changed"])
        b = copy.deepcopy(home)
        del b["hero_slides"][1]
        got = self.texts(diff.document(hf, home, b))
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].startswith("Banner slide 2 removed"), got)
        b = copy.deepcopy(home)
        b["hero_slides"].reverse()
        self.assertEqual(self.texts(diff.document(hf, home, b)), ["Banner slides reordered"])

    def test_units_groups_and_undescribed_keys(self):
        sf = self.S["settings"]["fields"]
        s = load("settings")
        b = copy.deepcopy(s)
        b["store"]["giftbox_volume_discount_percent"] = 33
        b["payments"]["cod"] = not s["payments"]["cod"]
        b["legacy"] = 1
        got = self.texts(diff.document(sf, s, b))
        self.assertIn("Gift box: box discount %d%% to 33%%" % s["store"]["giftbox_volume_discount_percent"], got)
        self.assertIn("Payments and tax: cash on delivery turned %s" % ("on" if b["payments"]["cod"] else "off"), got)
        self.assertIn("Other data changed (/legacy, not edited in the admin)", got)
        self.assertEqual(diff.summary([]), "No change")
        self.assertEqual(diff.pointer_label(self.S["home"]["fields"], "/hero_slides/2/image"), "Banner slide 3: picture")

    def test_commit_ids_are_checked_before_git_sees_them(self):
        for bad in ("--output=x", "HEAD", "abc", "g" * 40, "a" * 41, None):
            with self.assertRaises(ApiError):
                gitops.check_sha(bad)
        self.assertEqual(gitops.check_sha("deadbeef"), "deadbeef")


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = Box(PORT)
        cls.backups = cls.b.repo / "flow" / "content" / ".backups"

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def get(self, path):
        st, d = self.b.api("GET", path)
        self.assertEqual(st, 200, d)
        return d

    def history(self, resource):
        return self.get("history?resource=" + resource)

    def version(self, hid, resource):
        return self.get("history/%s?resource=%s" % (hid, resource))

    def craft(self, name, stamp, data):
        """A backup as an older admin left it."""
        self.backups.mkdir(parents=True, exist_ok=True)
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        (self.backups / ("%s.%s.json" % (name, stamp))).write_text(text, encoding="utf-8")

    def test_a_version_with_other_answers_cannot_move_their_keys(self):
        # A list whose entries carry a field the admin cannot change (a quiz
        # answer's key) cannot gain or lose an entry through a restore.
        cur = self.b.content("quiz")
        old = copy.deepcopy(cur)
        del old["answers"][-1]
        self.craft("quiz", "20200101-120000", old)
        h = self.history("documents/quiz")
        v = self.version("20200101-120000", "documents/quiz")
        self.assertIn("What each answer looks for: this version has %d and the site has %d"
                      % (len(old["answers"]), len(cur["answers"])), v["blocked"] or "")
        st, res = self.b.api("POST", "history/20200101-120000/restore", {"resource": "documents/quiz"}, rev=h["current_rev"])
        self.assertEqual(st, 409, res)
        self.assertEqual(res["error"]["code"], "cannot_restore")
        self.assertEqual(self.b.content("quiz"), cur)

    def test_a_version_with_other_slides_restores_onto_real_pictures(self):
        # Banner pictures are upload fields, so a version with another number
        # of slides can be restored, as long as every picture it names is a
        # file the site has: a picture that is gone is a 422 on its slide.
        b = self.b
        cur = b.content("home")
        fewer = copy.deepcopy(cur)
        del fewer["hero_slides"][-1]
        gone = copy.deepcopy(fewer)
        gone["hero_slides"][0]["image"] = "assets/img/banner-gone.jpg"
        self.craft("home", "20200101-120000", gone)
        self.craft("home", "20200101-120001", fewer)
        h = self.history("documents/home")
        self.assertIsNone(self.version("20200101-120000", "documents/home")["blocked"])
        st, res = b.api("POST", "history/20200101-120000/restore", {"resource": "documents/home"}, rev=h["current_rev"])
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/hero_slides/0/image", "missing_file")])
        self.assertEqual(b.content("home"), cur)
        st, res = b.api("POST", "history/20200101-120001/restore", {"resource": "documents/home"}, rev=h["current_rev"])
        self.assertEqual(st, 200, res)
        self.assertEqual(b.content("home")["hero_slides"], fewer["hero_slides"])
        st, res = b.api("PUT", "documents/home", {"data": cur}, rev=res["rev"])       # the slide back
        self.assertEqual(st, 200, res)
        self.assertEqual(b.content("home"), cur)

    def test_committed_versions(self):
        h = self.history("documents/home")
        git = [i for i in h["items"] if i["source"] == "git"]
        self.assertTrue(git)
        self.assertTrue(all(len(i["id"]) == 40 and i["subject"] and i["summary"] for i in git))
        v = self.version(git[-1]["id"][:10], "documents/home")
        self.assertEqual((v["source"], v["id"]), ("git", git[-1]["id"]))
        self.assertIsInstance(v["data"], dict)
        g = [i for i in self.history("products/be-mine")["items"] if i["source"] == "git"][0]
        self.assertEqual(self.version(g["id"], "products/be-mine")["data"]["name"], "Be Mine")
        for bad in ("deadbeef", "zzzz", "--output=x", "20201399-999999"):
            self.assertEqual(self.b.api("GET", "history/%s?resource=products/be-mine" % bad)[0], 404, bad)
        for bad in ("products/../x", "documents/nope", "", "products/Be-Mine"):
            self.assertEqual(self.b.api("GET", "history?resource=" + bad)[0], 400, bad)

    def test_document_restore_keeps_locked_fields_and_fills_missing_keys(self):
        b = self.b
        cur = b.content("settings")
        old = copy.deepcopy(cur)
        old["store"]["name"] = cur["store"]["name"] + " Old"
        old["payments"]["cod"] = not cur["payments"]["cod"]
        del old["store"]["sameday_cutoff"]
        self.craft("settings", "20200101-120000-000001", old)
        h = self.history("documents/settings")
        self.assertIn("20200101-120000-000001", [i["id"] for i in h["items"]])
        v = self.version("20200101-120000-000001", "documents/settings")
        self.assertEqual([k["path"] for k in v["kept"]], ["/payments/cod"])
        self.assertEqual(v["filled"], ["/store/sameday_cutoff"])
        st, res = b.api("POST", "history/20200101-120000-000001/restore", {"resource": "documents/settings"}, rev=h["current_rev"])
        self.assertEqual(st, 200, res)
        now = b.content("settings")
        self.assertEqual(now["store"]["name"], old["store"]["name"])
        self.assertEqual(now["payments"], cur["payments"])
        self.assertEqual(now["store"]["sameday_cutoff"], cur["store"]["sameday_cutoff"])
        self.assertEqual(list(now["store"]), list(cur["store"]))

    def test_document_save_summary_names_the_card(self):
        b = self.b
        d = self.get("documents/copy")
        data = copy.deepcopy(d["data"])
        data["quiz_banner"]["heading"] = "History test heading"
        st, res = b.api("PUT", "documents/copy", {"data": data}, rev=d["rev"])
        self.assertEqual(st, 200, res)
        local = [i for i in self.history("documents/copy")["items"] if i["source"] == "local"]
        self.assertTrue(local[0]["summary"].startswith("Scent quiz banner: heading"), local[0])

    def test_product_saves_are_versions_and_restore_is_a_save(self):
        b = self.b
        d = self.get("products/be-mine")
        p0 = d["data"]["price"]
        st, r1 = b.api("PUT", "products/be-mine", {"data": dict(d["data"], price=p0 + 5)}, rev=d["rev"])
        self.assertEqual(st, 200, r1)
        st, r2 = b.api("PUT", "products/be-mine", {"data": dict(r1["data"], price=p0 + 6)}, rev=r1["rev"])
        self.assertEqual(st, 200, r2)
        v = self.get("products/vibe")          # another product's save is not a version of this one
        st, _ = b.api("PUT", "products/vibe", {"data": dict(v["data"], stock=(v["data"].get("stock") or 0) + 1)}, rev=v["rev"])
        self.assertEqual(st, 200)
        h = self.history("products/be-mine")
        local = [i for i in h["items"] if i["source"] == "local"]
        self.assertEqual(len(local), 2, local)
        self.assertIn("Be Mine: price AED %d to AED %d" % (p0 + 5, p0 + 6), local[0]["summary"])
        self.assertIn("Be Mine: price AED %d to AED %d" % (p0, p0 + 5), local[1]["summary"])
        self.assertTrue(any(i["source"] == "git" and i.get("subject") for i in h["items"]))
        self.assertEqual(h["current_rev"], r2["rev"])
        v1 = self.version(local[1]["id"], "products/be-mine")
        self.assertEqual((v1["data"]["price"], v1["current_rev"]), (p0, r2["rev"]))
        price = [e for e in v1["diff"] if e["path"] == "/price"][0]
        self.assertEqual((price["before"], price["after"]), ("AED %d" % p0, "AED %d" % (p0 + 6)))
        self.assertEqual([e["text"] for e in v1["changes"]], ["Be Mine: price AED %d to AED %d" % (p0 + 6, p0)])
        path, body = "history/%s/restore" % local[1]["id"], {"resource": "products/be-mine"}
        self.assertEqual(b.api("POST", path, body)[0], 428)
        self.assertEqual(b.api("POST", path, body, rev=r1["rev"])[0], 412)
        st, res = b.api("POST", path, body, rev=r2["rev"])
        self.assertEqual(st, 200, res)
        self.assertTrue(res["build"]["ok"])
        self.assertEqual((res["kept"], b.content("products")["be-mine"]["price"]), ([], p0))
        local = [i for i in self.history("products/be-mine")["items"] if i["source"] == "local"]
        self.assertEqual(len(local), 3)       # the restore is a version too, so it can be undone
        self.assertIn("AED %d to AED %d" % (p0 + 6, p0), local[0]["summary"])

    def test_prune_keeps_the_newest_fifty_of_each_file(self):
        b = self.b
        nav = b.content("navigation")
        for i in range(55):
            self.craft("navigation", "2019%02d%02d-120000" % (i // 28 + 1, i % 28 + 1), nav)
        self.assertEqual(b.api("POST", "history/prune", {"days": 0})[0], 422)
        self.assertEqual(b.api("POST", "history/prune", {"days": "30"})[0], 422)
        st, res = b.api("POST", "history/prune", {"days": 30})
        self.assertEqual(st, 200, res)
        self.assertEqual(res["removed"], 5)
        left = sorted(p.name for p in self.backups.glob("navigation.*.json"))
        self.assertEqual((len(left), left[0]), (50, "navigation.20190106-120000.json"))
        self.assertGreaterEqual(self.get("history/backups")["files"], 50)

    def test_restore_keeps_what_the_admin_cannot_change(self):
        b = self.b
        products = b.content("products")
        pid = next(p for p, d in products.items() if d.get("category") == "edp" and p not in ("be-mine", "vibe")
                   and len(d.get("images", [])) > 1 and "badge" in d)
        cur = products[pid]
        old = copy.deepcopy(cur)
        old.update(price=cur["price"] + 7, images=list(reversed(cur["images"])), order=cur["order"] + 500,
                   never_discount=not cur["never_discount"], legacy_note="left by an older admin")
        del old["badge"]
        self.craft("products", "20200101-120000", dict(products, **{pid: old}))
        name = "products/" + pid
        h = self.history(name)
        self.assertEqual([i["source"] for i in h["items"] if i["id"] == "20200101-120000"], ["local"])
        v = self.version("20200101-120000", name)
        # photos are editable since the media stage, so their old order comes
        # back (each is still in the library); the product order stays
        self.assertEqual({k["path"] for k in v["kept"]}, {"/order", "/legacy_note"})
        self.assertEqual((v["filled"], v["guarded"], v["blocked"]), (["/badge"], ["never_discount"], None))
        self.assertFalse([e for e in v["changes"] if e["path"] in ("/order", "/legacy_note")])
        self.assertTrue([e for e in v["changes"] if e["path"] == "/images"])
        self.assertTrue([e for e in v["diff"] if e["path"] == "/images"])
        path = "history/20200101-120000/restore"
        self.assertEqual(b.api("POST", path, {"resource": name}, rev=h["current_rev"])[0], 428)
        st, res = b.api("POST", path, {"resource": name, "confirm_guarded": ["never_discount"]}, rev=h["current_rev"])
        self.assertEqual(st, 200, res)
        now = b.content("products")[pid]
        self.assertEqual((now["price"], now["never_discount"], now["badge"]), (cur["price"] + 7, old["never_discount"], ""))
        self.assertEqual((now["images"], now["order"]), (old["images"], cur["order"]))
        self.assertNotIn("legacy_note", now)
        self.assertEqual({k["path"] for k in res["kept"]}, {"/order", "/legacy_note"})

    def test_a_restored_photo_must_still_be_in_the_library(self):
        b = self.b
        products = b.content("products")
        # an attar, so the versions the other tests count stay theirs
        pid = next(p for p, d in products.items() if d.get("category") == "attars" and d.get("images"))
        cur = products[pid]
        old = copy.deepcopy(cur)
        old["images"] = [cur["images"][0], pid + "-99.jpg"]
        self.craft("products", "20200101-120002", dict(products, **{pid: old}))
        h = self.history("products/" + pid)
        st, res = b.api("POST", "history/20200101-120002/restore", {"resource": "products/" + pid}, rev=h["current_rev"])
        self.assertEqual(st, 422, res)
        self.assertEqual([(e["path"], e["code"]) for e in res["error"]["details"]], [("/images/1", "missing_file")])
        self.assertEqual(b.content("products")[pid], cur)


if __name__ == "__main__":
    unittest.main()
