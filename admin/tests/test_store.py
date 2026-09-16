"""The stores on their own, without a server: what export_snapshot returns,
the one rev function, the journal and recovery after a crash, the PostgreSQL
journal the JSON store must not guess about, the admin lock, busy, and what
a transaction records when the owner confirms a guarded change.

    /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_store.py'

Each test works on a temporary copy of flow/content: nothing is built, and
no server or port is used.
"""
import json
import pathlib
import shutil
import sys
import tempfile
import unittest

ADMIN = pathlib.Path(__file__).resolve().parent.parent
REPO = ADMIN.parent
sys.path.insert(0, str(ADMIN))
from bgsadmin import schema, service  # noqa: E402
from bgsadmin.config import Config  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402
from bgsadmin.jsonutil import canonical  # noqa: E402
from bgsadmin.store import base, files, jsonstore  # noqa: E402
from bgsadmin.store.jsonstore import JSONStore  # noqa: E402

NAMES = ["products", "settings", "copy", "home", "navigation", "pages", "quiz", "translations"]


class JSONStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgsstore-"))
        content = self.tmp / "flow" / "content"
        content.mkdir(parents=True)
        for name in NAMES:
            shutil.copy2(str(REPO / "flow" / "content" / (name + ".json")), str(content / (name + ".json")))
        self.cfg = Config(self.tmp)
        self.store = JSONStore(self.cfg)

    def tearDown(self):
        self.store.close()
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def path(self, name):
        return self.cfg.content_file(name)

    def craft(self, jid, state, snaps, gone=(), **more):
        """A journal as a save a crash cut short leaves it: snaps maps a path
        to the bytes it had before the save, gone lists files the save made."""
        d = self.cfg.backups / "txn" / jid
        d.mkdir(parents=True)
        entries = []
        for i, (p, data) in enumerate(snaps.items()):
            (d / ("%d.bin" % i)).write_bytes(data)
            entries.append({"path": str(p), "snap": "%d.bin" % i})
        entries += [{"path": str(p), "snap": None} for p in gone]
        man = dict({"state": state, "reason": "edit settings", "actor": "test", "files": entries}, **more)
        (d / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
        return d

    # ---- reading ---------------------------------------------------------------

    def test_export_snapshot_is_every_file_as_it_is_on_disk(self):
        # a file that differs from canonical form only in formatting shows as
        # such: the export is the raw bytes, not the data written again
        loose = json.dumps(json.loads(self.path("settings").read_bytes())).encode("utf-8")
        self.path("settings").write_bytes(loose)
        snap = self.store.export_snapshot()          # no open() needed: no lock, no recovery
        self.assertEqual(list(snap), NAMES)
        self.assertEqual(list(snap), list(base.content_names()))
        for name in NAMES:
            self.assertEqual(snap[name], self.path(name).read_bytes(), name)
        self.assertEqual(snap["settings"], loose)
        self.assertNotEqual(snap["settings"], canonical(json.loads(loose)))

    def test_one_rev_function_for_every_store(self):
        self.assertIs(jsonstore.rev_of, base.rev_of)
        raw = self.path("products").read_bytes()
        self.path("products").write_bytes(canonical(json.loads(raw)))
        self.store.open()
        data, rev = self.store.product("vibe")
        self.assertEqual(rev, base.rev_of(data))
        self.assertEqual(rev, base.sha(canonical(data))[:16])
        products, crev = self.store.products()
        # the collection rev: the file's hash, which is rev_of the dict in file order
        self.assertEqual(crev, base.sha(self.path("products").read_bytes())[:16])
        self.assertEqual(crev, base.rev_of(products))
        self.assertEqual(self.store.doc("quiz")[1], base.sha(self.path("quiz").read_bytes())[:16])
        with self.assertRaises(ApiError) as cm:
            self.store.product("no-such-product")
        self.assertEqual((cm.exception.status, cm.exception.code), (404, "not_found"))

    # ---- the journal and recovery -------------------------------------------------

    def test_a_journal_puts_back_what_it_copied(self):
        settings, made = self.path("settings"), self.tmp / "flow" / "made.txt"
        before = settings.read_bytes()
        j = files.Journal(self.cfg, [settings, made], {"reason": "edit settings", "actor": "test"})
        man = json.loads((j.dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(list(man), ["state", "reason", "actor", "files"])
        self.assertEqual((man["state"], [f["snap"] for f in man["files"]]), ("prepared", ["0.bin", None]))
        settings.write_bytes(b"{}\n")
        made.write_text("new")
        j.set_state("applied", stamp="20260914-120000-000000")
        man = json.loads((j.dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((man["state"], man["stamp"]), ("applied", "20260914-120000-000000"))
        j.restore()
        self.assertEqual(settings.read_bytes(), before)
        self.assertFalse(made.exists())
        self.assertEqual(files.journals(self.cfg), [(j.dir, man)])
        j.remove()
        self.assertEqual(files.journals(self.cfg), [])

    def test_recover_puts_an_interrupted_save_back(self):
        settings, home = self.path("settings"), self.path("home")
        old_settings, old_home = settings.read_bytes(), home.read_bytes()
        made = self.tmp / "flow" / "made-by-the-save.txt"
        a = self.craft("20260914-120000-000001-aaaaaa", "applied", {settings: old_settings}, gone=[made])
        p = self.craft("20260914-120000-000002-bbbbbb", "prepared", {home: old_home})
        c = self.craft("20260914-120000-000003-cccccc", "committed", {home: b"not put back"})
        settings.write_bytes(b'{"half": "written"}\n')
        made.write_text("new")
        self.assertEqual(self.store.open(), [a.name, p.name])
        self.assertEqual(settings.read_bytes(), old_settings)
        self.assertEqual(home.read_bytes(), old_home)
        self.assertFalse(made.exists())
        for d in (a, p, c):
            self.assertFalse(d.exists(), d.name)
        lines = [json.loads(x) for x in (self.cfg.backups / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(x["action"], x["txn"]) for x in lines], [("recover", a.name), ("recover", p.name)])

    def test_a_postgres_save_being_committed_is_left_for_the_database(self):
        # Only the database knows whether COMMIT went through: the JSON store
        # touches nothing, not even the other journal, and refuses to start.
        settings = self.path("settings")
        before = settings.read_bytes()
        a = self.craft("20260914-120000-000001-aaaaaa", "applied", {settings: b"{}\n"})
        c = self.craft("20260914-120000-000002-cccccc", "committing", {settings: b"{}\n"}, store="postgres",
                       txn="7d3c8f2e-4d0b-4c55-9a51-2f7f3f1b6a10", xid="1234", stamp="20260914-120000-000002")
        with self.assertRaises(SystemExit) as cm:
            self.store.open()
        self.assertIn("PostgreSQL", str(cm.exception))
        self.assertIn(c.name, str(cm.exception))
        self.assertEqual(settings.read_bytes(), before)
        self.assertTrue((a / "manifest.json").exists())
        self.assertTrue((c / "manifest.json").exists())
        self.assertTrue((c / "0.bin").exists())

    # ---- the lock, busy and confirm ---------------------------------------------------

    def test_one_admin_per_checkout_and_close_lets_the_next_one_in(self):
        self.store.open()
        other = JSONStore(self.cfg)
        with self.assertRaises(SystemExit):
            other.open()
        self.store.close()
        self.store.close()           # a second close does nothing
        try:
            other.open()
        finally:
            other.close()

    def test_a_second_save_is_busy_at_once(self):
        self.store.open()
        with self.store.transaction("first save") as txn:
            self.assertEqual(self.store.busy(), "first save")
            with self.assertRaises(ApiError) as cm:
                with self.store.transaction("second save"):
                    pass
            self.assertEqual((cm.exception.status, cm.exception.code), (423, "busy"))
        self.assertIsNone(self.store.busy())
        self.assertEqual(txn.result, {"changed": [], "build": None})

    def test_confirm_is_recorded(self):
        self.store.open()
        with self.store.transaction("edit vibe") as txn:
            txn.confirm("vibe", "never_discount")
            txn.confirm("vibe", "never_discount")
            txn.confirm("amore", "never_discount")
            # the PostgreSQL store hands these to the database as one
            # comma-separated setting: nothing else may get into it
            for pid, field in (("vibe,amore", "never_discount"), ("vibe", "never_discount,amore/never_discount"),
                               ("Vibe", "never_discount"), (5, "never_discount"), ("vibe", "")):
                with self.assertRaises(ValueError, msg=(pid, field)):
                    txn.confirm(pid, field)
        self.assertEqual(txn.confirmed, ["vibe/never_discount", "amore/never_discount"])
        self.assertEqual(txn.result, {"changed": [], "build": None})

    def test_saves_confirm_only_the_guarded_fields_they_change(self):
        fields = schema.load()["products"]["fields"]
        old = json.loads(self.path("products").read_bytes())["vibe"]

        class Recorder:
            def __init__(self):
                self.confirmed = []

            def confirm(self, pid, field):
                self.confirmed.append("%s/%s" % (pid, field))

        flipped = dict(old, never_discount=not old["never_discount"])
        for new, confirmed, want in ((flipped, ["never_discount"], ["vibe/never_discount"]),
                                     (dict(old, price=old["price"] + 1), ["never_discount"], []),
                                     (flipped, [], [])):
            t = Recorder()
            service.confirm(t, "vibe", fields, old, new, confirmed)
            self.assertEqual(t.confirmed, want, (new == flipped, confirmed))


if __name__ == "__main__":
    unittest.main()
