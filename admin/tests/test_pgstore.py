"""The PostgreSQL store: what only it does. Every other suite also runs on
it (ADMIN_TEST_STORE=postgres); this file covers the rest, on its own and
through the server:

- reads, revs and a save's order: the database first, then the files;
- the database's own refusals as backstops (never_discount, a locked
  setting, a bad price, a reference to no product, a product still named);
- busy: another save, another program's lock on the database;
- one admin per checkout and per database;
- the saves a crash cut short, settled at the next start;
- files changed outside the admin (refused for now), a database changed in
  psql, a missing file;
- the start refusals (exit status 2 and 3), the start lines, dbtool use.

    ADMIN_PGSTORE_PORT=4745 ADMIN_PG_PORT=5453 admin/.venv/bin/python -m unittest discover -s admin/tests -p 'test_pgstore.py'

Always PostgreSQL, on this run's throwaway cluster; skipped without psycopg or
PostgreSQL's programs. The servers it starts use ADMIN_PGSTORE_PORT and the
next port.
"""
import getpass
import itertools
import json
import os
import pathlib
import select
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

import box as boxmod
import cleanup
import pgcluster
from box import ADMIN, REPO, Box

sys.path.insert(0, str(ADMIN))
from bgsadmin import config  # noqa: E402
from bgsadmin.config import Config  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402
from bgsadmin.jsonutil import canonical  # noqa: E402
from bgsadmin.store import files  # noqa: E402
from bgsadmin.store.base import CannotStart, content_names, rev_of, sha  # noqa: E402

try:
    import psycopg
except ImportError:
    psycopg = None
if psycopg is not None:
    from bgsadmin.store.pgstore import PGStore  # noqa: E402

PORT = int(os.environ.get("ADMIN_PGSTORE_PORT", "4745"))
needs_db = unittest.skipUnless((pgcluster.BIN / "initdb").exists() and psycopg is not None,
                               "needs PostgreSQL's programs and psycopg (run it with admin/.venv/bin/python)")
_seq = itertools.count()


def dbtool(*args):
    return subprocess.run([sys.executable, str(ADMIN / "dbtool.py")] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=100, env=pgcluster.clean_env())


class Checkout:
    """This working tree's flow/ copied into a folder of its own and bound to
    a fresh database, which dbtool migrate --apply made as the owner would
    (so admin/local/store.json names it, as the admin's own role)."""

    def __init__(self, case, prefix="s"):
        self.c = pgcluster.cluster()
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgspgs-")).resolve()
        case.addCleanup(shutil.rmtree, str(tmp), True)
        self.repo = tmp / "repo"
        shutil.copytree(str(REPO / "flow"), str(self.repo / "flow"),
                        ignore=shutil.ignore_patterns(".backups", "__pycache__", ".*.tmp"))
        self.db = "%s_%d_%d" % (prefix, os.getpid() % 100000, next(_seq))
        self.owner = self.c.new_database(self.db)
        case.addCleanup(self.c.drop_database, self.db)
        p = dbtool("migrate", "--apply", "--dsn", self.owner, "--repo", self.repo)
        case.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.app = self.c.dsn(self.db, "bgs_corner_app")

    def cfg(self):
        return Config(self.repo, port=PORT, store="postgres", dsn=self.app)

    def file(self, name):
        return self.repo / "flow" / "content" / ("%s.json" % name)

    def q(self, sql, user="bgs_corner"):
        return self.c.psql(sql, dbname=self.db, user=user).strip()

    def psql_edit(self, key, change):
        """A document changed in psql, as the owner would: with who and why
        and its audit row."""
        with psycopg.connect(self.owner) as conn:
            t = str(uuid.uuid4())
            conn.execute("SELECT set_config('bgs.txn', %s, true), set_config('bgs.actor', 'tester', true), "
                         "set_config('bgs.reason', 'edited in psql', true)", (t,))
            d = json.loads(conn.execute("SELECT body::text FROM bgs.documents WHERE key = %s", (key,)).fetchone()[0])
            change(d)
            conn.execute("UPDATE bgs.documents SET body = %s::json WHERE key = %s",
                         (json.dumps(d, ensure_ascii=False, separators=(",", ":")), key))
            conn.execute("INSERT INTO bgs.audit_log (txn, actor, action, resources, ok) "
                         "VALUES (%s, 'tester', 'edited in psql', %s::text[], true)", (t, [key]))
        return d


def craft(cfg, jid, state, snaps, **more):
    """A journal as a save a crash cut short leaves it: snaps maps a path to
    the bytes it had before the save."""
    d = cfg.backups / "txn" / jid
    d.mkdir(parents=True)
    entries = []
    for i, (p, data) in enumerate(snaps.items()):
        (d / ("%d.bin" % i)).write_bytes(data)
        entries.append({"path": str(p), "snap": "%d.bin" % i})
    man = dict({"state": state, "reason": "a crafted save", "actor": "tester", "files": entries}, **more)
    (d / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return d


@unittest.skipUnless(psycopg is not None, "needs psycopg (run it with admin/.venv/bin/python)")
class OutcomeTests(unittest.TestCase):
    """How a save that was committing when the admin stopped is settled, from
    the database's two answers: the save's ok audit row, read with the
    statement's snapshot, and its transaction's status, read at call time."""

    def decide(self, answers):
        from bgsadmin.store import pgstore
        rows = iter(answers)

        class Conn:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def execute(self, sql, args):
                return self

            def fetchone(self):
                return next(rows)

        real = pgstore.connect.connect
        pgstore.connect.connect = lambda dsn, autocommit=False: Conn()
        self.addCleanup(setattr, pgstore.connect, "connect", real)
        store = PGStore.__new__(PGStore)
        store.dsn, store.params = "", {}
        return store._outcome({"txn": "t1", "xid": "7"})

    def test_a_commit_that_lands_between_the_two_reads_was_kept(self):
        # no row yet in the snapshot, but committed by the time the status is read
        self.assertTrue(self.decide([(False, "committed")]))

    def test_the_row_or_the_status_decides(self):
        self.assertTrue(self.decide([(True, "committed")]))
        self.assertTrue(self.decide([(False, "in progress"), (False, "committed")]))
        self.assertFalse(self.decide([(False, "aborted")]))
        self.assertFalse(self.decide([(False, None)]))


@needs_db
class StoreTests(unittest.TestCase):
    """The store in this process, with no server."""

    def open(self, co):
        s = PGStore(co.cfg())
        self.addCleanup(s.close)
        s.open()
        return s

    def save(self, s, reason, change, name="products", confirm=()):
        with s.transaction(reason) as txn:
            d = txn.load(name)
            change(d)
            txn.put(name, d)
            for pid, field in confirm:
                txn.confirm(pid, field)
        return txn

    def test_reads_are_the_files_and_the_revs_are_the_json_stores(self):
        co = Checkout(self)
        s = self.open(co)
        products, crev = s.products()
        self.assertEqual(list(products), list(json.loads(co.file("products").read_bytes())))
        self.assertEqual(crev, sha(co.file("products").read_bytes())[:16])
        d, rev = s.product("vibe")
        self.assertEqual(rev, rev_of(d))
        self.assertEqual(s.doc("quiz")[1], sha(co.file("quiz").read_bytes())[:16])
        # home.json is written by hand in HEAD: its rev is its canonical form's
        self.assertEqual(s.doc("home")[1], rev_of(json.loads(co.file("home").read_bytes())))
        self.assertEqual(s.export_snapshot()["products"], co.file("products").read_bytes())
        self.assertEqual(list(s.export_snapshot()), list(content_names()))
        self.assertEqual(s.external_changes(), [])
        for call in (lambda: s.product("no-such-product"), lambda: s.doc("nothing")):
            with self.assertRaises(ApiError) as cm:
                call()
            self.assertEqual((cm.exception.status, cm.exception.code), (404, "not_found"))
        self.assertEqual(s.describe(), "PostgreSQL %s as bgs_corner_app (18.6)" % co.db)
        self.assertEqual(s.warnings(), [])

    def test_a_save_writes_the_database_then_the_files(self):
        co = Checkout(self)
        s = self.open(co)
        before = co.file("products").read_bytes()
        old = json.loads(before)["vibe"]["price"]

        def up(p):
            p["vibe"]["price"] += 1
            # reads inside the block see the content from before the save
            self.assertEqual(s.product("vibe")[0]["price"], old)
        txn = self.save(s, "edit vibe", up)
        self.assertEqual(txn.result["changed"], ["products"])
        self.assertTrue(txn.result["build"]["ok"])
        self.assertEqual(s.product("vibe")[0]["price"], old + 1)
        self.assertEqual(json.loads(co.file("products").read_bytes())["vibe"]["price"], old + 1)
        self.assertEqual(s.export_snapshot()["products"], co.file("products").read_bytes())
        self.assertEqual(co.q("SELECT actor || ' ' || reason FROM bgs.revisions WHERE entity_id = 'vibe' "
                              "ORDER BY id DESC LIMIT 1"), "%s edit vibe" % getpass.getuser())
        self.assertEqual(co.q("SELECT action || ' ' || ok || ' ' || array_to_string(resources, ',') FROM "
                              "bgs.audit_log ORDER BY id DESC LIMIT 1"), "edit vibe true products")
        backups = sorted(co.cfg().backups.glob("products.*.json"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), before)
        self.assertEqual(files.journals(co.cfg()), [])
        self.assertEqual(s.external_changes(), [])
        # an unchanged save writes nothing and builds nothing
        self.assertEqual(self.save(s, "no change", lambda p: None).result, {"changed": [], "build": None})
        p = dbtool("verify", "--repo", co.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)

    def test_the_database_refuses_what_gets_past_the_admin(self):
        co = Checkout(self)
        s = self.open(co)
        before = {n: co.file(n).read_bytes() for n in content_names()}
        version = co.q("SELECT version FROM bgs.content_state")
        quizzed = co.q("SELECT product_id FROM bgs.product_refs WHERE resource = 'quiz' ORDER BY ptr LIMIT 1")

        def flip(p):
            p["vibe"]["never_discount"] = not p["vibe"]["never_discount"]

        def price(p):
            p["vibe"]["price"] = 0

        def ghost(p):
            p["vibe"]["related"] = ["ghost"]

        def gone(p):
            del p[quizzed]

        for label, name, change, want in (
                ("never_discount, nobody confirmed", "products", flip, (428, "guarded_field")),
                ("a price of 0", "products", price, (422, "validation")),
                ("a product related to no product", "products", ghost, (422, "validation")),
                ("a product the quiz names, removed", "products", gone, (409, "referenced")),
                ("VAT 5", "settings", lambda d: d["store"].update(vat_rate_percent=5), (403, "locked_field"))):
            with self.assertRaises(ApiError, msg=label) as cm:
                self.save(s, label, change, name)
            self.assertEqual((cm.exception.status, cm.exception.code), want, label)
        errs = {}
        for change in (price, ghost):
            with self.assertRaises(ApiError) as cm:
                self.save(s, "again", change)
            errs[change.__name__] = [(e.get("path"), e.get("code"), e.get("id")) for e in cm.exception.details]
        self.assertEqual(errs, {"price": [("/price", "db_rule", "vibe")], "ghost": [("/related/0", "unknown_product", "vibe")]})
        # nothing was written: not the database, not a file, no journal
        self.assertEqual(co.q("SELECT version FROM bgs.content_state"), version)
        self.assertEqual({n: co.file(n).read_bytes() for n in content_names()}, before)
        self.assertEqual(files.journals(co.cfg()), [])
        # confirmed, the same change goes through
        self.save(s, "confirmed", flip, confirm=[("vibe", "never_discount")])
        self.assertNotEqual(json.loads(co.file("products").read_bytes())["vibe"]["never_discount"],
                            json.loads(before["products"])["vibe"]["never_discount"])

    def test_busy_another_save_and_another_program(self):
        co = Checkout(self)
        s = self.open(co)
        with s.transaction("first save") as txn:
            self.assertEqual(s.busy(), "first save")
            with self.assertRaises(ApiError) as cm:
                with s.transaction("second save"):
                    pass
            self.assertEqual((cm.exception.status, cm.exception.code), (423, "busy"))
        self.assertIsNone(s.busy())
        self.assertEqual(txn.result, {"changed": [], "build": None})

        def up(p):
            p["vibe"]["price"] += 1
        # another program holding the save lock: busy at once
        with psycopg.connect(co.owner, autocommit=True) as other:
            other.execute("SELECT pg_advisory_lock(16967, 2)")
            with self.assertRaises(ApiError) as cm:
                self.save(s, "while locked", up)
            self.assertEqual((cm.exception.status, cm.exception.code, cm.exception.details),
                             (423, "busy", {"operation": "another program using the database"}))
            other.execute("SELECT pg_advisory_unlock(16967, 2)")
        # a transaction in psql holding the content version: the save waits
        # for lock_timeout, then says busy
        with psycopg.connect(co.owner) as other:
            other.execute("SELECT bgs.lock_content_state()")
            t0 = time.monotonic()
            with self.assertRaises(ApiError) as cm:
                self.save(s, "while held", up)
            self.assertEqual((cm.exception.status, cm.exception.code), (423, "busy"))
            self.assertGreater(time.monotonic() - t0, 4)
            other.rollback()
        self.assertEqual(files.journals(co.cfg()), [])
        self.save(s, "now free", up)

    def test_one_admin_per_checkout_and_per_database(self):
        co = Checkout(self)
        s = self.open(co)
        with self.assertRaises(CannotStart) as cm:
            PGStore(co.cfg()).open()
        self.assertIn("Another admin is already running for", cm.exception.message)
        s.close()
        with psycopg.connect(co.owner, autocommit=True) as holder:
            holder.execute("SELECT pg_advisory_lock(16967, 1)")
            with self.assertRaises(CannotStart) as cm:
                PGStore(co.cfg()).open()
            self.assertEqual(cm.exception.status, 2)
            self.assertIn("Another admin is already using the database %s" % co.db, cm.exception.message)
        self.open(co)

    def test_the_saves_a_crash_cut_short_are_settled_at_start(self):
        co = Checkout(self)
        cfg = co.cfg()
        cfg.backups.mkdir(parents=True, exist_ok=True)
        settings, home, copy_ = co.file("settings"), co.file("home"), co.file("copy")
        old = {p: p.read_bytes() for p in (settings, home, copy_)}
        # applied, then the process died: COMMIT was never sent
        a = craft(cfg, "20260914-120000-000001-aaaaaa", "applied", {settings: old[settings]})
        settings.write_bytes(b'{"half": "written"}\n')
        # committing, and the database kept it: its audit row is there
        kept = str(uuid.uuid4())
        co.q("INSERT INTO bgs.audit_log (txn, actor, action, ok) VALUES ('%s', 'tester', 'edit home', true)" % kept)
        k = craft(cfg, "20260914-120000-000002-bbbbbb", "committing", {home: b'{"before": true}\n'}, store="postgres",
                  txn=kept, xid=None, stamp="20260914-120000-000002", written=["home"])
        # committing, and the database did not keep it: no audit row, its transaction aborted
        with psycopg.connect(co.owner) as conn:
            xid = conn.execute("SELECT pg_current_xact_id()::text").fetchone()[0]
            conn.rollback()
        g = craft(cfg, "20260914-120000-000003-cccccc", "committing", {copy_: old[copy_]}, store="postgres",
                  txn=str(uuid.uuid4()), xid=xid, stamp="20260914-120000-000003", written=["copy"])
        copy_.write_bytes(b'{"never": "committed"}\n')
        s = PGStore(cfg)
        self.addCleanup(s.close)
        self.assertEqual(s.open(), [a.name, k.name, g.name])
        self.assertEqual(s.kept, [k.name])
        self.assertEqual(settings.read_bytes(), old[settings])
        self.assertEqual(copy_.read_bytes(), old[copy_])
        self.assertEqual(home.read_bytes(), old[home])                   # kept as the save left it
        self.assertEqual((cfg.backups / "home.20260914-120000-000002.json").read_bytes(), b'{"before": true}\n')
        self.assertEqual(sorted(cfg.backups.glob("*.json")), [cfg.backups / "home.20260914-120000-000002.json"])
        self.assertEqual(files.journals(cfg), [])
        lines = [json.loads(x) for x in (cfg.backups / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([(x["action"], x["txn"]) for x in lines],
                         [("recover", a.name), ("recover-forward", k.name), ("recover", g.name)])
        self.assertEqual(s.external_changes(), [])


# ---- through the server --------------------------------------------------------------------

@needs_db
class ServerTests(unittest.TestCase):
    """A Box on the PostgreSQL store, whatever ADMIN_TEST_STORE says."""

    @classmethod
    def setUpClass(cls):
        boxmod.STORE = "postgres"
        cls.b = Box(PORT)

    @classmethod
    def tearDownClass(cls):
        cls.b.close()

    def path(self, name):
        return self.b.repo / "flow" / "content" / ("%s.json" % name)

    def status(self):
        st, s = self.b.api("GET", "status")
        self.assertEqual(st, 200, s)
        return s

    def price(self, pid, delta):
        st, d = self.b.api("GET", "products/" + pid)
        self.assertEqual(st, 200, d)
        return self.b.api("PUT", "products/" + pid, {"data": dict(d["data"], price=d["data"]["price"] + delta)},
                          rev=d["rev"])

    def owner(self):
        return psycopg.connect(self.b.cluster.dsn(self.b.db))

    def test_a_file_changed_outside_the_admin_is_refused_until_it_is_put_back(self):
        path = self.path("products")
        orig = path.read_bytes()
        d = json.loads(orig)
        d["vibe"]["name"] = "Vibe by hand"
        path.write_bytes(canonical(d))
        try:
            self.assertEqual(self.status()["external"], ["products"])
            st, res = self.price("amore", 1)
            self.assertEqual((st, res["error"]["code"]), (409, "changed_outside"), res)
            self.assertEqual(res["error"]["details"], {"names": ["products"]})
            self.assertIn("git checkout -- flow/content/products.json", res["error"]["message"])
            self.assertEqual(json.loads(path.read_bytes())["vibe"]["name"], "Vibe by hand")
            self.assertEqual(self.b.api("POST", "status/ack", {})[1]["external"], ["products"])
        finally:
            path.write_bytes(orig)
        self.assertEqual(self.status()["external"], [])
        st, res = self.price("amore", 1)
        self.assertEqual(st, 200, res)

    def test_the_same_data_written_another_way_is_in_sync(self):
        path = self.path("quiz")
        orig = path.read_bytes()
        path.write_bytes(json.dumps(json.loads(orig)).encode("utf-8"))
        try:
            self.assertEqual(self.status()["external"], [])
        finally:
            path.write_bytes(orig)
        self.assertEqual(self.status()["external"], [])

    def test_a_change_made_in_psql_is_listed_and_rebuild_now_writes_it(self):
        with self.owner() as conn:
            t = str(uuid.uuid4())
            conn.execute("SELECT set_config('bgs.txn', %s, true), set_config('bgs.actor', 'tester', true), "
                         "set_config('bgs.reason', 'edited in psql', true)", (t,))
            conn.execute("UPDATE bgs.documents SET body = (substr(body::text, 1, length(body::text) - 1) || "
                         "',\"x_note\":\"from psql\"}')::json WHERE key = 'copy'")
            conn.execute("INSERT INTO bgs.audit_log (txn, actor, action, resources, ok) "
                         "VALUES (%s, 'tester', 'edited in psql', '{copy}', true)", (t,))
        self.assertEqual(self.status()["external"], ["copy"])
        self.assertNotIn("x_note", json.loads(self.path("copy").read_bytes()))
        st, res = self.b.api("POST", "build", {})
        self.assertEqual((st, res.get("changed")), (200, ["copy"]), res)
        self.assertEqual(json.loads(self.path("copy").read_bytes())["x_note"], "from psql")
        self.assertEqual(self.status()["external"], [])

    def test_a_missing_file_is_listed_and_written_again(self):
        path = self.path("translations")
        orig = path.read_bytes()
        path.unlink()
        self.assertEqual(self.status()["external"], ["translations"])
        st, res = self.b.api("POST", "build", {})
        self.assertEqual((st, res.get("changed")), (200, ["translations"]), res)
        self.assertEqual(path.read_bytes(), orig)
        self.assertEqual(self.status()["external"], [])

    def test_a_build_that_fails_keeps_nothing_in_the_database(self):
        sized = self.b.repo / "flow" / "assets" / "img" / "amore-1-600.jpg"
        saved = sized.read_bytes()
        with self.owner() as conn:
            version = conn.execute("SELECT version FROM bgs.content_state").fetchone()[0]
        before = self.b.api("GET", "products/amore")[1]
        sized.unlink()
        try:
            st, res = self.price("amore", 2)
            self.assertEqual((st, res["error"]["code"]), (422, "build_failed"), res)
        finally:
            sized.write_bytes(saved)
        with self.owner() as conn:
            self.assertEqual(conn.execute("SELECT version FROM bgs.content_state").fetchone()[0], version)
            ok, problems = conn.execute("SELECT ok, problems::text FROM bgs.audit_log ORDER BY id DESC LIMIT 1").fetchone()
        self.assertFalse(ok)
        self.assertIn("amore-1-600", problems)
        self.assertEqual(self.b.api("GET", "products/amore")[1]["rev"], before["rev"])


@needs_db
class StartTests(unittest.TestCase):
    """server.py in PostgreSQL mode: what it refuses and with which exit
    status, and what it says when it starts."""

    def command(self, repo, args, py=None):
        return [py or sys.executable, str(ADMIN / "server.py"), "--port", str(PORT + 1), "--repo", str(repo),
                "--no-push"] + [str(a) for a in args]

    def refused(self, repo, says, *args, status=2, py=None):
        t0 = time.monotonic()
        p = subprocess.run(self.command(repo, args, py), capture_output=True, text=True, timeout=30,
                           env=pgcluster.clean_env())
        self.assertEqual(p.returncode, status, p.stdout + p.stderr)
        self.assertIn(says, p.stderr)
        return time.monotonic() - t0

    def started(self, repo, *args):
        """The lines a server prints as it starts; then it is stopped."""
        p = subprocess.Popen(self.command(repo, args), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             env=pgcluster.clean_env())
        net = cleanup.on_exit(lambda: p.poll() is None and p.kill())
        buf = b""
        try:
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                ready, _, _ = select.select([p.stdout], [], [], 0.5)
                if not ready:
                    if b"\nstore " in b"\n" + buf or p.poll() is not None:
                        break
                    continue
                chunk = os.read(p.stdout.fileno(), 4096)
                if not chunk:
                    break
                buf += chunk
        finally:
            if p.poll() is None:
                p.terminate()
            p.wait(10)
            p.stdout.close()
            cleanup.forget(net)
        return buf.decode("utf-8", "replace").splitlines()

    def fresh(self, co):
        name = "f_%d_%d" % (os.getpid() % 100000, next(_seq))
        dsn = co.c.new_database(name)
        self.addCleanup(co.c.drop_database, name)
        return dsn

    def test_refusals_come_before_anything_changes(self):
        co = Checkout(self)
        other = pathlib.Path(tempfile.mkdtemp(prefix="bgspgs-other-")).resolve()
        self.addCleanup(shutil.rmtree, str(other), True)
        shutil.copytree(str(co.repo / "flow" / "content"), str(other / "flow" / "content"))
        pg = ("--store", "postgres", "--dsn")
        self.refused(co.repo, "holds a password", *pg, co.app + " password=secret")
        self.refused(co.repo, "absolute path", "--dsn", co.app.replace("host=/", "host="))
        self.refused(co.repo, "a superuser", *pg, co.c.dsn(co.db, "postgres"))
        self.refused(co.repo, "no admin tables yet", *pg, self.fresh(co))
        self.refused(other, "belongs to the checkout %s, not %s" % (co.repo, other), *pg, co.app)
        secs = self.refused(co.repo, "PostgreSQL is not answering", *pg, "host=%s port=%d dbname=%s user=bgs_corner_app"
                            % (co.c.sock, co.c.port + 1, co.db), status=3)
        self.assertLess(secs, 5)
        # admin/local/store.json says postgres: the admin will not start without psycopg
        self.refused(co.repo, "needs psycopg", py="/usr/bin/python3")
        with psycopg.connect(co.owner, autocommit=True) as holder:
            holder.execute("SELECT pg_advisory_lock(16967, 1)")
            self.refused(co.repo, "Another admin is already using the database %s" % co.db)
        local = config.store_file(other)
        local.parent.mkdir(parents=True)
        local.write_text("{not json", encoding="utf-8")
        self.refused(other, "is not valid JSON")
        self.assertFalse((co.cfg().backups / "txn").exists() and list((co.cfg().backups / "txn").iterdir()))

    def test_it_says_which_store_it_runs_on(self):
        co = Checkout(self)
        lines = self.started(co.repo)
        self.assertIn("store       PostgreSQL %s as bgs_corner_app (18.6)" % co.db, lines)
        self.assertEqual([l for l in lines if l.startswith("warning")], [])
        lines = self.started(co.repo, "--store", "postgres", "--dsn", co.owner)
        self.assertIn("store       PostgreSQL %s as bgs_corner (18.6)" % co.db, lines)
        self.assertTrue(any(l.startswith("warning     running as bgs_corner, the database's owner") for l in lines), lines)
        self.assertIn("store       JSON files in flow/content", self.started(co.repo, "--store", "json"))

    def test_dbtool_use_chooses_the_store_the_checkout_starts_on(self):
        co = Checkout(self)
        p = dbtool("use", "json", "--repo", co.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(config.read_store_choice(co.repo), {"store": "json", "dsn": co.app})
        self.assertIn("store       JSON files in flow/content", self.started(co.repo))
        p = dbtool("use", "postgres", "--dsn", self.fresh(co), "--repo", co.repo)
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        self.assertIn("no admin tables yet", p.stderr)
        self.assertEqual(config.read_store_choice(co.repo), {"store": "json", "dsn": co.app})
        p = dbtool("use", "postgres", "--repo", co.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("store       PostgreSQL %s as bgs_corner_app (18.6)" % co.db, self.started(co.repo))


if __name__ == "__main__":
    unittest.main()
