"""The admin's PostgreSQL side, with no admin server. So far: the throwaway
clusters every PostgreSQL test runs on (pgcluster.py). The migrations and
the database's own refusals join this file with migration 001.

    ADMIN_PG_PORT=5453 /usr/bin/python3 -m unittest discover -s admin/tests -p 'test_dbschema.py'

Needs PostgreSQL's programs (initdb, pg_ctl and psql) in /opt/homebrew/bin
or ADMIN_PG_BIN, and no database driver. It never touches the shared server:
each cluster is its own, in a private folder, with no TCP. The two runs it
starts as child processes use port ADMIN_PG_PORT + 1.
"""
import os
import pathlib
import shutil
import signal
import subprocess
import sys
import time
import unittest

import pgcluster

TESTS = pathlib.Path(__file__).resolve().parent

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


@unittest.skipUnless((pgcluster.BIN / "initdb").exists(), "PostgreSQL's programs are not installed")
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


if __name__ == "__main__":
    unittest.main()
