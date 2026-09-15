"""The admin's PostgreSQL side, with no admin server: the throwaway clusters
every PostgreSQL test runs on (pgcluster.py), migration 001 with its runner
(dbtool migrate and verify), and the database's own refusals.

    ADMIN_PG_PORT=5453 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_dbschema.py'
    ADMIN_PG_PORT=5453 admin/.venv/bin/python -m unittest discover -s admin/tests -p 'test_dbschema.py'

The cluster tests need PostgreSQL's programs (initdb, pg_ctl and psql) in
/opt/homebrew/bin or ADMIN_PG_BIN, and no database driver. Everything else
needs psycopg, so it runs under the admin's virtualenv and is skipped under
/usr/bin/python3. It never touches the shared server: each cluster is its
own, in a private folder, with no TCP. The runs it starts as child processes
use port ADMIN_PG_PORT + 1.
"""
import fcntl
import itertools
import json
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

import cleanup
import pgcluster

TESTS = pathlib.Path(__file__).resolve().parent
ADMIN = TESTS.parent
REPO = ADMIN.parent
sys.path.insert(0, str(ADMIN))
from bgsadmin.jsonutil import canonical  # noqa: E402
from bgsadmin.store.base import CannotStart, content_names, sha  # noqa: E402

try:
    import psycopg
except ImportError:
    psycopg = None
if psycopg is not None:
    from bgsadmin.db import content, migrate  # noqa: E402

HAVE_PG = (pgcluster.BIN / "initdb").exists()
needs_db = unittest.skipUnless(HAVE_PG and psycopg is not None,
                               "needs PostgreSQL's programs and psycopg (run it with admin/.venv/bin/python)")

# A test run that starts a cluster and then ends as `end` makes it end.
CHILD = """
import os, signal, sys, time
sys.path.insert(0, %(tests)r)
import pgcluster
c = pgcluster.Cluster(port=%(port)d).start(app_role=False)
print(c.root, int((c.data / "postmaster.pid").read_text().split()[0]), flush=True)
%(end)s
time.sleep(60)
"""


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


@unittest.skipUnless(HAVE_PG, "PostgreSQL's programs are not installed")
class ClusterTests(unittest.TestCase):
    def test_a_cluster_is_private_and_goes_when_stopped(self):
        c = pgcluster.Cluster().start()
        root = c.root
        try:
            self.assertTrue(c.socket.exists())
            self.assertLessEqual(len(str(c.socket)), pgcluster.SOCKET_MAX)
            self.assertEqual(root.stat().st_mode & 0o777, 0o700)

            def q(sql, **kw):
                return c.psql(sql, **kw).strip()
            self.assertEqual(q("SHOW listen_addresses"), "")
            self.assertEqual(q("SHOW port"), str(c.port))
            self.assertEqual(q("SHOW unix_socket_directories"), str(root))
            self.assertEqual(q("SELECT string_agg(format('%s %s %s %s', rolname, rolsuper, rolcreatedb, rolcreaterole), "
                               "',' ORDER BY rolname) FROM pg_roles WHERE rolname LIKE 'bgs%'"),
                             "bgs_corner f f f,bgs_corner_app f f f")
            dsn = c.new_database("t_acl")
            self.assertEqual(dsn, "host=%s port=%d dbname=t_acl user=bgs_corner" % (root, c.port))
            # made as the owner's database was: owned by bgs_corner, CONNECT taken from PUBLIC
            self.assertEqual(q("SELECT pg_get_userbyid(datdba), datacl::text, datcollate FROM pg_database "
                               "WHERE datname = 't_acl'"), "bgs_corner|{=T/bgs_corner,bgs_corner=CTc/bgs_corner}|C")
            self.assertEqual(q("SELECT current_user", dbname="t_acl", user="bgs_corner"), "bgs_corner")
            with self.assertRaises(RuntimeError):      # the app role connects once a migration grants it
                c.psql("SELECT 1", dbname="t_acl", user="bgs_corner_app")
            with self.assertRaises(ValueError):
                c.new_database("t; DROP DATABASE postgres")
            c.drop_database("t_acl")
            self.assertEqual(q("SELECT count(*) FROM pg_database WHERE datname = 't_acl'"), "0")
        finally:
            c.stop()
        self.assertFalse(root.exists())

    def test_the_folders_of_a_run_that_is_gone_are_swept_and_nothing_else(self):
        gone = int(subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"],
                                  capture_output=True, text=True, check=True).stdout)
        made = []
        try:
            for owner, marked in ((gone, True), (os.getpid(), True), (gone, False)):
                d = pgcluster._new_root(pgcluster.ROOT, pgcluster.PORT)
                made.append(d)
                (d / "owner.pid").write_text(str(owner))
                if marked:
                    (d / pgcluster.MARK).write_text("")
            pgcluster.sweep()
            self.assertEqual([d.exists() for d in made], [False, True, True])
        finally:
            for d in made:
                shutil.rmtree(str(d), ignore_errors=True)

    def child(self, end):
        p = subprocess.Popen([sys.executable, "-c", CHILD % {"tests": str(TESTS), "port": pgcluster.PORT + 1, "end": end}],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = p.stdout.readline().split()
        if len(line) != 2:
            p.kill()
            p.wait(10)
            self.fail("the child run did not start its cluster: %s" % p.stderr.read())
        return p, pathlib.Path(line[0]), int(line[1])

    def test_a_run_that_dies_of_the_alarm_leaves_no_cluster(self):
        # SIGALRM is what the 110 s limit on a test command sends, and Python
        # dies of it without running atexit: the handler stops the cluster first
        p, root, pid = self.child("signal.alarm(1)")
        p.wait(30)
        self.assertEqual(p.returncode, -signal.SIGALRM, p.stderr.read())
        self.assertFalse(alive(pid))
        self.assertFalse(root.exists())

    def test_a_killed_run_leaves_no_cluster(self):
        # nothing catches SIGKILL: the watchdog stops the cluster once the run is gone
        p, root, pid = self.child("os.kill(os.getpid(), signal.SIGKILL)")
        p.wait(30)
        self.assertEqual(p.returncode, -signal.SIGKILL)
        for _ in range(100):
            if not alive(pid) and not root.exists():
                break
            time.sleep(0.1)
        self.assertFalse(alive(pid))
        self.assertFalse(root.exists())


# ---- helpers for the database tests -------------------------------------------------

_seq = itertools.count()
_checkout = None


def checkout():
    """One checkout for this run's databases to be bound to: this working
    tree's flow/ copied into a folder of its own, gone when the run ends."""
    global _checkout
    if _checkout is None:
        tmp = tempfile.mkdtemp(prefix="bgsdb-")
        cleanup.on_exit(lambda: shutil.rmtree(tmp, ignore_errors=True))
        _checkout = pathlib.Path(tmp).resolve() / "repo"
        shutil.copytree(str(REPO / "flow"), str(_checkout / "flow"),
                        ignore=shutil.ignore_patterns(".backups", "__pycache__", ".*.tmp"))
    return _checkout


def dbtool(*args):
    return subprocess.run([sys.executable, str(ADMIN / "dbtool.py")] + [str(a) for a in args],
                          capture_output=True, text=True, timeout=100, env=pgcluster.clean_env())


def compact(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


class DatabaseCase(unittest.TestCase):
    """Fresh databases on this run's cluster, dropped after each test."""

    @classmethod
    def setUpClass(cls):
        cls.c = pgcluster.cluster()
        cls.repo = checkout()

    def fresh(self, prefix="t"):
        name = "%s_%d_%d" % (prefix, os.getpid() % 100000, next(_seq))
        dsn = self.c.new_database(name)
        self.addCleanup(self.c.drop_database, name)
        return name, dsn

    def migrated(self, prefix="t"):
        """A fresh database with dbtool migrate --apply run on it, as the owner would."""
        name, dsn = self.fresh(prefix)
        p = dbtool("migrate", "--apply", "--dsn", dsn, "--repo", self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        return name, dsn

    def q(self, name, sql, user="bgs_corner"):
        return self.c.psql(sql, dbname=name, user=user).strip()

    def files(self, repo=None):
        return {n: ((repo or self.repo) / "flow" / "content" / ("%s.json" % n)).read_bytes() for n in content_names()}


@needs_db
class MigrateTests(DatabaseCase):
    """dbtool migrate and verify, run as the owner runs them."""

    def test_a_dry_run_proves_everything_and_writes_nothing(self):
        name, dsn = self.fresh()
        p = dbtool("migrate", "--dsn", dsn, "--repo", self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("DRY RUN: nothing was written", p.stdout)
        self.assertIn("applied     001_foundation.sql", p.stdout)
        self.assertIn("clean room  the site built from the database's export", p.stdout)
        for n, raw in self.files().items():
            line = [l for l in p.stdout.splitlines() if l.split()[:1] == [n + ".json"]]
            self.assertEqual(len(line), 1, n)
            # home.json is written by hand in HEAD: the same data, other formatting
            self.assertTrue(line[0].endswith("identical" if canonical(json.loads(raw)) == raw
                                             else "formatting only: the same data"), line[0])
        self.assertEqual(self.q(name, "SELECT count(*) FROM pg_namespace WHERE nspname = 'bgs'"), "0")

    def test_apply_loads_the_content_the_database_gives_back_and_a_second_apply_does_nothing(self):
        name, dsn = self.migrated()
        files = self.files()
        products = json.loads(files["products"])
        self.assertEqual(self.q(name, "SELECT (SELECT count(*) FROM bgs.products) || ' ' || (SELECT count(*) FROM "
                                      "bgs.documents) || ' ' || (SELECT count(*) FROM bgs.audit_log)"),
                         "%d 7 1" % len(products))
        self.assertEqual(self.q(name, "SELECT version || ' ' || name FROM bgs.schema_migrations"), "1 001_foundation.sql")
        self.assertEqual(self.q(name, "SELECT repo_path FROM bgs.store_meta"), str(self.repo))
        with psycopg.connect(dsn) as conn:
            state = content.read(conn.cursor())
        self.assertEqual(list(state.products), list(products))          # file order kept
        for n, raw in files.items():
            self.assertEqual(state.exports[n], canonical(json.loads(raw)), n)
            if canonical(json.loads(raw)) == raw:
                self.assertEqual(state.exports[n], raw, n)
            # the base: the file and the export as they were when they agreed
            self.assertEqual(state.bases[n], (sha(raw), sha(state.exports[n])), n)
        revs = self.q(name, "SELECT count(*) FROM bgs.revisions")
        p = dbtool("migrate", "--apply", "--dsn", dsn, "--repo", self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("Nothing to do", p.stdout)
        self.assertEqual(self.q(name, "SELECT (SELECT count(*) FROM bgs.audit_log) || ' ' || "
                                      "(SELECT count(*) FROM bgs.revisions)"), "1 %s" % revs)
        p = dbtool("verify", "--dsn", self.c.dsn(name, "bgs_corner_app"), "--repo", self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertIn("admin role  bgs_corner_app: reads everything", p.stdout)
        self.assertIn("OK: the database agrees", p.stdout)

    def test_verify_says_which_side_changed(self):
        name, dsn = self.migrated()
        # the database is bound to the shared checkout: edit a file there and
        # put it back
        path = self.repo / "flow" / "content" / "quiz.json"
        before = path.read_bytes()
        self.addCleanup(path.write_bytes, before)
        path.write_bytes(before + b"\n")
        p = dbtool("verify", "--dsn", dsn, "--repo", self.repo)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("quiz.json: changed in the file.", p.stdout)
        path.write_bytes(before)
        with psycopg.connect(dsn) as conn:
            cur = conn.cursor()
            t = uuid.uuid4()
            content.begin(cur, t, "tester", "edit copy in psql")
            cur.execute("UPDATE bgs.documents SET body = (substr(body::text, 1, length(body::text) - 1) || "
                        "',\"x_note\":\"from psql\"}')::json WHERE key = 'copy'")
            content.audit(cur, t, "tester", "edit copy in psql", ["copy"])
        p = dbtool("verify", "--dsn", dsn, "--repo", self.repo)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(p.stdout.split("1 difference:")[-1].strip(), "copy.json: changed in the database.")

    def test_an_edited_migration_a_newer_schema_and_a_gap_are_refused(self):
        name, dsn = self.migrated()
        folder = pathlib.Path(tempfile.mkdtemp(prefix="bgsdb-mig-"))
        self.addCleanup(shutil.rmtree, str(folder), True)
        mine = migrate.FOLDER / "001_foundation.sql"
        with psycopg.connect(dsn) as conn:
            cur = conn.cursor()
            shutil.copy2(str(mine), str(folder / mine.name))
            self.assertEqual(migrate.pending(cur, folder), [])
            (folder / mine.name).write_bytes(mine.read_bytes() + b"\n-- one more line\n")
            with self.assertRaises(CannotStart) as cm:
                migrate.pending(cur, folder)
            self.assertIn("an applied migration was edited", cm.exception.message)
            (folder / mine.name).unlink()
            with self.assertRaises(CannotStart) as cm:
                migrate.pending(cur, folder)
            self.assertIn("newer than this checkout", cm.exception.message)
            shutil.copy2(str(mine), str(folder / mine.name))
            (folder / "003_later.sql").write_text("SELECT 1;\n")
            with self.assertRaises(CannotStart) as cm:
                migrate.pending(cur, folder)
            self.assertIn("without gaps", cm.exception.message)
            with self.assertRaises(CannotStart):
                migrate.check_current(cur, pathlib.Path("/elsewhere"))
            migrate.check_current(cur, self.repo)

    def test_the_database_belongs_to_one_checkout(self):
        name, dsn = self.migrated()
        other = pathlib.Path(tempfile.mkdtemp(prefix="bgsdb-other-")).resolve()
        self.addCleanup(shutil.rmtree, str(other), True)
        shutil.copytree(str(self.repo / "flow" / "content"), str(other / "flow" / "content"))
        for args in (("migrate", "--apply", "--dsn", dsn), ("migrate", "--dsn", dsn)):
            p = dbtool(*args, "--repo", other)
            self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
            self.assertIn("belongs to the checkout %s, not %s" % (self.repo, other), p.stderr)
        p = dbtool("verify", "--dsn", dsn, "--repo", other)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertIn("The database belongs to %s, not this checkout" % self.repo, p.stdout)
        self.assertEqual(self.q(name, "SELECT repo_path FROM bgs.store_meta"), str(self.repo))

    def test_refusals_before_anything_is_written(self):
        name, dsn = self.fresh()
        base = self.c.dsn(name, "bgs_corner")

        def refused(dsn_, says, status=2, cmd="migrate"):
            p = dbtool(cmd, "--dsn", dsn_, "--repo", self.repo)
            self.assertEqual(p.returncode, status, "%s\n%s%s" % (dsn_, p.stdout, p.stderr))
            self.assertIn(says, p.stderr)
        refused(self.c.dsn(name, "postgres"), "a superuser")
        refused(base + " password=secret", "holds a password")
        refused(base.replace("host=/", "host="), "absolute path")
        refused("host=%s port=%d dbname=%s" % (self.c.sock, self.c.port, name), "must name its own user")
        refused(self.c.dsn(name, "bgs_corner_app"), "refused the connection")      # CONNECT is not granted yet
        refused("host=%s/nothing-here port=%d dbname=%s user=bgs_corner" % (self.c.sock, self.c.port, name),
                "PostgreSQL is not answering", 3)
        self.q(name, "CREATE TABLE public.orders (id integer)")
        refused(base, "tables that are not the admin's (public.orders)")
        self.assertEqual(self.q(name, "SELECT count(*) FROM pg_namespace WHERE nspname = 'bgs'"), "0")
        self.q(name, "DROP TABLE public.orders")
        # an admin running on the checkout holds its lock
        lock = self.repo / "flow" / "content" / ".backups"
        lock.mkdir(exist_ok=True)
        with open(str(lock / ".admin.lock"), "a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            refused(base, "An admin is running")
            fcntl.flock(f, fcntl.LOCK_UN)
        self.assertEqual(self.q(name, "SELECT count(*) FROM pg_namespace WHERE nspname = 'bgs'"), "0")
        p = dbtool("migrate", "--apply", "--dsn", base, "--repo", self.repo)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        refused(self.c.dsn(name, "bgs_corner_app"), "does not own")          # granted now, but not the owner


# ---- the database's own refusals ---------------------------------------------------------

def who(cur, reason="battery", confirmed=""):
    t = str(uuid.uuid4())
    cur.execute("SELECT set_config('bgs.txn', %s, true), set_config('bgs.actor', 'tester', true), "
                "set_config('bgs.reason', %s, true), set_config('bgs.confirmed', %s, true)", (t, reason, confirmed))
    return t


def audited(cur, t):
    cur.execute("INSERT INTO bgs.audit_log (txn, actor, action, resources, ok) "
                "VALUES (%s, 'tester', 'battery', '{}', true)", (t,))


def body_of(cur, table, key):
    col = "id" if table == "products" else "key"
    return json.loads(cur.execute("SELECT body::text FROM bgs.%s WHERE %s = %%s" % (table, col), (key,)).fetchone()[0])


def edit(table, key, change, confirmed="", audit=True):
    """A transaction that changes one product or document as change(data) says."""
    col = "id" if table == "products" else "key"

    def fn(cur):
        t = who(cur, "edit %s" % key, confirmed)
        d = body_of(cur, table, key)
        change(d)
        cur.execute("UPDATE bgs.%s SET body = %%s::json WHERE %s = %%s" % (table, col), (compact(d), key))
        if audit:
            audited(cur, t)
    return fn


def raw(sql, *params):
    """One statement, with who and why and its audit row."""
    def fn(cur):
        t = who(cur)
        cur.execute(sql, params or None)
        audited(cur, t)
    return fn


def put(*path, value):
    def change(d):
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
    return change


def drop(*path):
    def change(d):
        for k in path[:-1]:
            d = d[k]
        del d[path[-1]]
    return change


def attempt(dsn, fn):
    """Run fn(cursor) in one transaction that ends as the admin's saves do
    (SET CONSTRAINTS ALL IMMEDIATE, then COMMIT); what refused it, or
    "accepted"."""
    conn = psycopg.connect(dsn)
    try:
        with conn.cursor() as cur:
            fn(cur)
            cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
        conn.commit()
        return "accepted"
    except psycopg.Error as e:
        conn.rollback()
        return ("%s %s" % (e.sqlstate, e.diag.constraint_name or "")).strip()
    finally:
        conn.close()


@needs_db
class RefusalTests(DatabaseCase):
    """The writes the database refuses by itself, and some it must accept, as
    the owner and as the admin's own role: the build plan's battery."""

    def ids(self, dsn):
        with psycopg.connect(dsn) as conn:
            def one(sql):
                return conn.execute(sql).fetchone()[0]
            return {"P": "vibe", "other": "amore",
                    "other_order": one("SELECT sort_order FROM bgs.products WHERE id = 'amore'"),
                    "attar": one("SELECT id FROM bgs.products WHERE category = 'attars' ORDER BY pos LIMIT 1"),
                    "edp": one("SELECT id FROM bgs.products WHERE category = 'edp' ORDER BY pos LIMIT 1"),
                    "quizzed": one("SELECT product_id FROM bgs.product_refs WHERE resource = 'quiz' ORDER BY ptr LIMIT 1")}

    def battery(self, ids, app):
        P, other = ids["P"], ids["other"]

        def roles(owner, app_role):
            return app_role if app else owner

        def prod(change, **kw):
            return edit("products", P, change, **kw)

        def doc(key, change):
            return edit("documents", key, change)

        def price_up(d):
            d["price"] += 1

        def flip(d):
            d["never_discount"] = not d["never_discount"]

        def name_then_add(cur):
            t = who(cur, "create and name")
            q = body_of(cur, "documents", "quiz")
            q["profiles"][0]["product"] = "brand-new"
            cur.execute("UPDATE bgs.documents SET body = %s::json WHERE key = 'quiz'", (compact(q),))
            d = dict(body_of(cur, "products", P), order=99999, name="Brand new", related=[])
            cur.execute("INSERT INTO bgs.products (id, body) VALUES ('brand-new', %s::json)", (compact(d),))
            audited(cur, t)

        def reverse_edp(cur):
            t = who(cur, "reorder")
            rows = [(i, json.loads(b)) for i, b in cur.execute(
                "SELECT id, body::text FROM bgs.products WHERE category = 'edp' ORDER BY sort_order").fetchall()]
            for (i, d), o in zip(rows, reversed([d["order"] for _, d in rows])):
                d["order"] = o
                cur.execute("UPDATE bgs.products SET body = %s::json WHERE id = %s", (compact(d), i))
            audited(cur, t)

        def trigger_off_and_on(cur):
            cur.execute("ALTER TABLE bgs.products DISABLE TRIGGER products_before")
            cur.execute("ALTER TABLE bgs.products ENABLE TRIGGER products_before")

        slash = chr(92)
        return [
            ("no who and why", lambda c: c.execute("UPDATE bgs.products SET pos = pos + 1000 WHERE id = %s", (P,)),
             "55000"),
            ("no audit row", prod(price_up, audit=False), "23514 revisions_audited"),
            ("a price change", prod(price_up), "accepted"),
            ("price 0", prod(put("price", value=0)), "23514 products_price"),
            ("price as text", prod(put("price", value="85")), "23514 products_price"),
            ("price 85.5", prod(put("price", value=85.5)), "23514 products_body_sane"),
            ("price 85.0", raw("UPDATE bgs.products SET body = regexp_replace(body::text, %s, %s)::json WHERE id = %s",
                               '"price":([0-9]+)', '"price":' + slash + "1.0", P), "23514 products_body_sane"),
            ("stock as text", prod(put("stock", value="5")), "23514 products_stock"),
            ("stock -1", prod(put("stock", value=-1)), "23514 products_stock"),
            ("stock null", prod(put("stock", value=None)), "accepted"),
            ("a script tag in the name", prod(put("name", value="Vibe <script>")), "23514 products_text_clean"),
            ("a long dash in the story", prod(put("story", value=["a " + chr(0x2014) + " b"])), "23514 products_text_clean"),
            ("a tab in the name", prod(put("name", value="Vi\tbe")), "23514 products_text_clean"),
            ("%% in the story", prod(put("story", value=["5%% off"])), "23514 products_text_clean"),
            ("a name of 61 characters", prod(put("name", value="x" * 61)), "23514 products_name"),
            ("category perfume", prod(put("category", value="perfume")), "23514 products_category"),
            ("published removed", prod(drop("published")), "23514 products_published"),
            ("published yes", prod(put("published", value="yes")), "23514 products_published"),
            ("never_discount flipped, nobody confirmed", prod(flip), "23514 products_never_discount_guarded"),
            ("never_discount flipped, another product confirmed", prod(flip, confirmed="%s/never_discount" % other),
             "23514 products_never_discount_guarded"),
            ("never_discount flipped and confirmed", prod(flip, confirmed="%s/never_discount" % P), "accepted"),
            ("and flipped back, confirmed", prod(flip, confirmed="%s/never_discount" % P), "accepted"),
            ("a key twice", raw("UPDATE bgs.products SET body = (%s || substr(body::text, 2))::json WHERE id = %s",
                                '{"name":"A","name":"B",', P), "23514 products_body_sane"),
            ("NUL in a string", prod(put("name", value="Vi" + chr(0) + "be")), "22P05"),
            ("half of a UTF-16 pair", raw("UPDATE bgs.products SET body = (%s || substr(body::text, 2))::json "
                                          "WHERE id = %s", '{"x":"' + slash + 'ud800",', P), "22P0"),
            ("an attar priced at none of its sizes", edit("products", ids["attar"], price_up), "23514 products_attar_sizes"),
            ("an attar with no sizes", edit("products", ids["attar"], put("sizes", value=[])), "23514 products_attar_sizes"),
            ("an attar with one label twice", edit("products", ids["attar"],
                                                   lambda d: d.update(sizes=[d["sizes"][0], dict(d["sizes"][0])])),
             "23514 products_attar_sizes"),
            ("an EDP without a gender", edit("products", ids["edp"], put("gender", value="")), "23514 products_edp"),
            ("related to itself", prod(put("related", value=[P])), "23514 products_not_related"),
            ("related to a missing product", prod(put("related", value=["no-such-thing"])), "23503 product_refs_target"),
            ("deleting a product the quiz names", raw("DELETE FROM bgs.products WHERE id = %s", ids["quizzed"]),
             "23503 product_refs_target"),
            ("the id admin", raw("INSERT INTO bgs.products (id, body) SELECT 'admin', body FROM bgs.products "
                                 "WHERE id = %s", P), "23514 products_id_format"),
            ("an id ending in a line break", raw("INSERT INTO bgs.products (id, body) SELECT %s, body FROM "
                                                 "bgs.products WHERE id = %s", P + "-2\n", P), "23514 products_id_format"),
            ("an id renamed", raw("UPDATE bgs.products SET id = %s WHERE id = %s", P + "-x", P),
             roles("23514 products_id_fixed", "42501")),
            ("an order twice", prod(put("order", value=ids["other_order"])), "23505 products_order_unique"),
            ("a product named, then added", name_then_add, "accepted"),
            ("the EDP order reversed", reverse_edp, "accepted"),
            ("two file positions swapped", raw(
                "UPDATE bgs.products SET pos = CASE id WHEN %s THEN (SELECT pos FROM bgs.products WHERE id = %s) "
                "ELSE (SELECT pos FROM bgs.products WHERE id = %s) END WHERE id IN (%s, %s)", P, other, P, P, other),
             "accepted"),
            ("VAT 0", doc("settings", put("store", "vat_rate_percent", value=0)), "23514 documents_locked_values"),
            ("cash on delivery off", doc("settings", put("payments", "cod", value=False)), "23514 documents_locked_values"),
            ("card payments removed", doc("settings", drop("payments", "card")), "23514 documents_locked_values"),
            ("a GA4 id typed in", doc("settings", put("analytics", "ga4_id", value="G-123")),
             "23514 documents_locked_values"),
            ("the store's name", doc("settings", put("store", "name", value="BGS Corner Test")), "accepted"),
            ("a locked value changed on its own", lambda c: c.execute(
                "UPDATE bgs.locked_values SET value = '0' WHERE ptr = '/store/vat_rate_percent'"),
             roles("23514 locked_values_held", "42501")),
            ("a link to no product", doc("navigation", put("x_link", value="product.html?p=ghost")),
             "23503 product_refs_target"),
            ("markup in a translation key", doc("translations", lambda d: d["ar"].update({"<b>": "x"})),
             "23514 documents_text_clean"),
            ("a document deleted", raw("DELETE FROM bgs.documents WHERE key = 'copy'"),
             roles("23514 documents_kept", "42501")),
            ("a revision rewritten", lambda c: c.execute(
                "UPDATE bgs.revisions SET reason = 'x' WHERE id = (SELECT min(id) FROM bgs.revisions)"),
             roles("23514", "42501")),
            ("the audit log deleted", lambda c: c.execute("DELETE FROM bgs.audit_log"), roles("23514", "42501")),
            ("revisions truncated", lambda c: c.execute("TRUNCATE bgs.revisions"), roles("23514", "42501")),
            ("a revision written by hand", lambda c: c.execute(
                "INSERT INTO bgs.revisions (txn, actor, reason, resource, entity_id, op, version, body) VALUES "
                "(gen_random_uuid(), 'x', 'x', 'copy', '_', 'update', 1, '{}')"),
             roles("23514 revisions_audited", "42501")),
            ("a trigger switched off (and on)", trigger_off_and_on, roles("accepted", "42501")),
            ("session_replication_role", lambda c: c.execute("SET session_replication_role = replica"), "42501"),
            ("the content version read FOR UPDATE", lambda c: c.execute(
                "SELECT version FROM bgs.content_state FOR UPDATE"), roles("accepted", "42501")),
            ("the content version locked the admin's way", lambda c: c.execute("SELECT bgs.lock_content_state()"),
             "accepted"),
            ("old revisions pruned", lambda c: c.execute("SELECT bgs.prune_revisions('1000 days', 50)"), "accepted"),
            # what only the admin's own role is refused: the owner may do these by design
            ("a locked value changed", lambda c: c.execute(
                "UPDATE bgs.locked_values SET value = '0' WHERE ptr = '/store/cod_fee'"), roles(None, "42501")),
            ("a reference field added", lambda c: c.execute("INSERT INTO bgs.ref_fields VALUES ('copy', '/x')"),
             roles(None, "42501")),
            ("the checkout rebound", lambda c: c.execute("UPDATE bgs.store_meta SET repo_path = '/tmp/x'"),
             roles(None, "42501")),
            ("a version set by hand", raw("UPDATE bgs.products SET version = 1 WHERE id = %s", P), roles(None, "42501")),
            ("a table created", lambda c: c.execute("CREATE TABLE bgs.x (a integer)"), roles(None, "42501")),
        ]

    def run_battery(self, role):
        name, dsn = self.migrated("b")
        ids = self.ids(dsn)
        run = self.c.dsn(name, role)
        out = []
        for label, fn, want in self.battery(ids, role == "bgs_corner_app"):
            if want is None:
                continue
            got = attempt(run, fn)
            if not (got == want if want == "accepted" else got.startswith(want)):
                out.append("%s: wanted %s, got %s" % (label, want, got))
        self.assertEqual(out, [], "\n".join(out))
        self.assertEqual(self.q(name, "SELECT count(*) FROM bgs.products WHERE id = 'brand-new'"), "1")

    def test_as_the_owner(self):
        self.run_battery("bgs_corner")

    def test_as_the_admins_own_role(self):
        self.run_battery("bgs_corner_app")


@needs_db
class RoundTripTests(DatabaseCase):
    """What the database keeps comes back exactly: the export is the file."""

    def test_awkward_text_and_numbers_come_back_exactly(self):
        name, dsn = self.migrated("h")
        arabic = "".join(chr(c) for c in (0x639, 0x637, 0x631, 0x20, 0x645, 0x633, 0x643))
        awkward = {"zeta": 1, "alpha": 2, "b": {"z": [1, 2], "a": None}, "arabic": arabic, "face": chr(0x1F600),
                   "lines": "one\ntwo", "quote": 'say "hi"', "slash": "a" + chr(92) + "b", "big": 2 ** 70,
                   "empty_object": {}, "empty_list": [], "nothing": None, "no": False}
        with psycopg.connect(dsn) as conn:
            cur = conn.cursor()
            base = content.read(cur)
            pid = next(p for p, d in base.products.items() if d["category"] == "bakhoor")
            new = dict(base.products[pid], name="Awkward", order=99001, related=[], x_awkward=awkward)
            doc = dict(base.docs["copy"], x_awkward=awkward)
            t = uuid.uuid4()
            content.begin(cur, t, "tester", "awkward values")
            cur.execute("INSERT INTO bgs.products (id, body) VALUES ('awkward', %s::json)", (compact(new),))
            cur.execute("UPDATE bgs.documents SET body = %s::json WHERE key = 'copy'", (compact(doc),))
            content.audit(cur, t, "tester", "awkward values", ["products", "copy"])
        with psycopg.connect(self.c.dsn(name, "bgs_corner_app")) as conn:
            state = content.read(conn.cursor())
        self.assertEqual(compact(state.products["awkward"]), compact(new))      # every key in its order, every value
        self.assertEqual(list(state.products)[-1], "awkward")                   # added at the end of the file
        self.assertEqual(state.exports["products"], canonical(dict(base.products, awkward=new)))
        self.assertEqual(state.exports["copy"], canonical(doc))
        self.assertEqual(json.loads(state.exports["copy"])["x_awkward"]["big"], 2 ** 70)

    def test_numbers_are_whole_keys_single_and_text_whole_characters(self):
        name, dsn = self.migrated("n")
        spelled = "UPDATE bgs.products SET body = regexp_replace(body::text, %s, %s)::json WHERE id = 'vibe'"
        for label, fn, want in (
                ("1e2", raw(spelled, '"price":([0-9]+)', '"price":1e2'), "23514 products_body_sane"),
                ("5.0", raw(spelled, '"price":([0-9]+)', '"price":5.0'), "23514 products_body_sane"),
                ("a key twice", raw("UPDATE bgs.products SET body = ('{\"name\":\"A\",' || substr(body::text, 2))::json "
                                    "WHERE id = 'vibe'"), "23514 products_body_sane"),
                ("NUL", edit("documents", "copy", put("x_nul", value=chr(0))), "22P05"),
                ("half of a pair", raw("UPDATE bgs.documents SET body = (%s || substr(body::text, 2))::json "
                                       "WHERE key = 'copy'", '{"x":"' + chr(92) + 'udc00",'), "22P0")):
            self.assertTrue(attempt(dsn, fn).startswith(want), label)


# The child's save: it dies just before COMMIT, or just after (argv: DSN, product id, before or after).
CRASH = """
import json, os, sys, uuid
import psycopg
conn = psycopg.connect(sys.argv[1])
cur = conn.cursor()
pid, t = sys.argv[2], str(uuid.uuid4())
cur.execute("SELECT set_config('bgs.txn', %s, true), set_config('bgs.actor', 'tester', true), "
            "set_config('bgs.reason', 'crash test', true)", (t,))
d = json.loads(cur.execute("SELECT body::text FROM bgs.products WHERE id = %s", (pid,)).fetchone()[0])
d["price"] += 1
cur.execute("UPDATE bgs.products SET body = %s::json WHERE id = %s",
            (json.dumps(d, ensure_ascii=False, separators=(",", ":")), pid))
cur.execute("INSERT INTO bgs.audit_log (txn, actor, action, resources, ok) "
            "VALUES (%s, 'tester', 'crash test', '{products}', true)", (t,))
cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
xid = cur.execute("SELECT pg_current_xact_id()::text").fetchone()[0]
if sys.argv[3] == "after":
    conn.commit()
print(json.dumps({"txn": t, "xid": xid}), flush=True)
os._exit(0)
"""


@needs_db
class DumpAndCrashTests(DatabaseCase):
    def export(self, dsn):
        with psycopg.connect(dsn) as conn:
            return content.read(conn.cursor()).exports

    def tool(self, *args):
        p = self.c._tool(*args, timeout=90)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_the_admins_role_dumps_and_the_owner_restores(self):
        name, dsn = self.migrated("d")
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="bgsdb-dump-"))
        self.addCleanup(shutil.rmtree, str(tmp), True)
        dump = tmp / "b.dump"
        where = ("-h", self.c.sock, "-p", self.c.port)
        # the app role reads the identity sequences, which pg_dump needs
        self.tool("pg_dump", "-Fc", *where, "-U", "bgs_corner_app", "-d", name, "-f", dump)
        before = self.export(dsn)
        fresh, _ = self.fresh("r")
        self.tool("pg_restore", *where, "-U", "bgs_corner", "-d", fresh, "--single-transaction", "--exit-on-error", dump)
        with self.assertRaises(RuntimeError):         # a dump holds no database-wide grant
            self.q(fresh, "SELECT 1", user="bgs_corner_app")
        self.q(fresh, "SELECT bgs.grant_app_role()")
        self.assertEqual(self.export(self.c.dsn(fresh, "bgs_corner_app")), before)
        # in place: a product taken out comes back, and the admin's role keeps its rights
        gone = self.q(name, "SELECT id FROM bgs.products AS p WHERE NOT EXISTS (SELECT 1 FROM bgs.product_refs AS r "
                            "WHERE r.product_id = p.id) ORDER BY pos DESC LIMIT 1")
        with psycopg.connect(dsn) as conn:
            cur = conn.cursor()
            t = uuid.uuid4()
            content.begin(cur, t, "tester", "take one out")
            cur.execute("DELETE FROM bgs.products WHERE id = %s", (gone,))
            content.audit(cur, t, "tester", "take one out", ["products"])
        self.assertNotEqual(self.export(dsn), before)
        self.tool("pg_restore", *where, "-U", "bgs_corner", "-d", name, "--clean", "--if-exists",
                  "--single-transaction", "--exit-on-error", dump)
        self.assertEqual(self.export(dsn), before)
        self.assertEqual(self.q(name, "SELECT has_table_privilege('bgs_corner_app', 'bgs.products', 'DELETE'), "
                                      "has_table_privilege('bgs_corner_app', 'bgs.locked_values', 'UPDATE')"), "t|f")

    def test_the_database_says_whether_a_save_that_died_was_kept(self):
        # recover() asks this on a fresh connection when a save died while
        # committing: its audit_log row, and pg_xact_status of its xid
        name, dsn = self.migrated("x")
        pid = self.q(name, "SELECT id FROM bgs.products WHERE category <> 'attars' ORDER BY pos LIMIT 1")
        old = int(self.q(name, "SELECT price FROM bgs.products WHERE id = '%s'" % pid))
        for when, want in (("before", ("aborted", 0, old)), ("after", ("committed", 1, old + 1))):
            p = subprocess.run([sys.executable, "-c", CRASH, self.c.dsn(name, "bgs_corner_app"), pid, when],
                               capture_output=True, text=True, timeout=60, env=pgcluster.clean_env())
            info = json.loads(p.stdout.strip().splitlines()[-1])
            for _ in range(100):
                with psycopg.connect(dsn) as conn:
                    got = conn.execute("SELECT pg_xact_status(%s::xid8), (SELECT count(*) FROM bgs.audit_log WHERE "
                                       "txn = %s), (SELECT price FROM bgs.products WHERE id = %s)",
                                       (info["xid"], info["txn"], pid)).fetchone()
                if got[0] != "in progress":
                    break
                time.sleep(0.05)
            self.assertEqual(tuple(got), want, when)


if __name__ == "__main__":
    unittest.main()
