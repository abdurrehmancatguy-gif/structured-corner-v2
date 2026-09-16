"""The server plumbing other areas build on: raw-body uploads, non-JSON
responses and background jobs. Runs a bare server with two routes of its own
on port 4732, against no repository content at all."""
import http.client
import json
import os
import pathlib
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import jobs  # noqa: E402
from bgsadmin.config import Config  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402
from bgsadmin.httpd import Handler, Server  # noqa: E402
from bgsadmin.routes import Raw, Route  # noqa: E402

PORT = int(os.environ.get("ADMIN_PLUMBING_PORT", "4732"))
BOX_PORT = int(os.environ.get("ADMIN_PLUMBING_BOX_PORT", "4733"))
TESTS = pathlib.Path(__file__).resolve().parent

# A test run that starts a Box and then ends as `end` makes it end.
BOX_RUN = """
import os, signal, sys, time
sys.path.insert(0, %(tests)r)
from box import Box
b = Box(%(port)d, overlay=False)
print(b.proc.pid, b.tmp, flush=True)
%(end)s
time.sleep(60)
"""


def upload(req):
    fd, path = tempfile.mkstemp()
    os.close(fd)
    n = req.save_body(path)
    data = pathlib.Path(path).read_bytes()
    os.unlink(path)
    return {"type": req.content_type, "bytes": n, "head": data[:4].decode("latin-1")}


def download(req):
    return Raw(b"\xef\xbb\xbfid,name\r\nvibe,Vibe\r\n", "text/csv; charset=utf-8",
               {"Content-Disposition": 'attachment; filename="products.csv"'})


class FakeApp:
    admin_enabled = True

    def __init__(self):
        self.cfg = Config(tempfile.gettempdir(), port=PORT)
        self.token = "test-token"
        self.routes = [Route("POST", r"up", upload, body="raw", types={"image/png"}, limit=64),
                       Route("GET", r"down", download)]


class PlumbingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server(("127.0.0.1", PORT), Handler, FakeApp())
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        h = {"Host": "localhost:%d" % PORT, "X-Admin-Token": "test-token", "Origin": "http://localhost:%d" % PORT}
        h.update(headers or {})
        c.request(method, "/admin/api/v1/" + path, body=body, headers=h)
        r = c.getresponse()
        out = r.status, dict(r.getheaders()), r.read()
        c.close()
        return out

    def test_raw_upload_is_typed_sized_and_streamed(self):
        st, _, body = self.req("POST", "up", b"\x89PNG0123", {"Content-Type": "image/png"})
        self.assertEqual(st, 200, body)
        got = json.loads(body)
        self.assertEqual((got["type"], got["bytes"], got["head"]), ("image/png", 8, "\x89PNG"))
        self.assertEqual(self.req("POST", "up", b"abc", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.req("POST", "up", b"x" * 65, {"Content-Type": "image/png"})[0], 413)
        self.assertEqual(self.req("POST", "up", b"", {"Content-Type": "image/png"})[0], 400)

    def test_raw_response_keeps_the_security_headers(self):
        st, hd, body = self.req("GET", "down")
        self.assertEqual(st, 200)
        self.assertTrue(body.startswith(b"\xef\xbb\xbfid,name"))
        self.assertEqual(hd.get("Content-Type"), "text/csv; charset=utf-8")
        self.assertIn("products.csv", hd.get("Content-Disposition", ""))
        self.assertEqual(hd.get("Cache-Control"), "no-store")
        self.assertIn("frame-ancestors 'none'", hd.get("Content-Security-Policy", ""))

    def test_a_raw_route_must_declare_types_and_a_limit(self):
        with self.assertRaises(ValueError):
            Route("POST", r"x", upload, body="raw")

    def test_jobs_report_results_and_failures(self):
        ok = jobs.start("test", lambda log: (log("working"), {"n": 1})[1])
        bad = jobs.start("test", lambda log: (_ for _ in ()).throw(ApiError(422, "nope", "It did not work.")))
        for _ in range(50):
            if ok.finished and bad.finished:
                break
            time.sleep(0.05)
        self.assertEqual(ok.view()["state"], "done")
        self.assertEqual(ok.view()["result"], {"n": 1})
        self.assertEqual(ok.view()["log_tail"], ["working"])
        self.assertEqual(bad.view()["state"], "failed")
        self.assertEqual(bad.view()["error"]["code"], "nope")
        self.assertIs(jobs.get(ok.id), ok)


class ImportTests(unittest.TestCase):
    def test_json_mode_loads_no_database_driver(self):
        # PostgreSQL mode needs psycopg and the admin's venv; JSON mode runs on
        # the standard library, so starting the admin, loading every API
        # module and the JSON store must not import the driver
        code = ("import sys; sys.path.insert(0, %r); import bgsadmin.app, bgsadmin.routes as r, "
                "bgsadmin.store.jsonstore; r.load(); "
                "print(sorted(m for m in sys.modules if m.split('.')[0].startswith('psycopg')))") % str(REPO / "admin")
        p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, "[]"), p.stderr)

    def test_the_postgresql_code_compiles_under_this_python(self):
        # PostgreSQL mode runs on the admin's virtualenv, Python 3.9 too: its
        # modules must stay 3.9-clean, checked here where psycopg is missing
        import py_compile
        admin = REPO / "admin"
        files = ([admin / "dbtool.py", admin / "bgsadmin" / "store" / "pgstore.py"]
                 + sorted((admin / "bgsadmin" / "db").glob("*.py")))
        with tempfile.TemporaryDirectory() as d:
            for i, f in enumerate(files):
                py_compile.compile(str(f), cfile=os.path.join(d, "%d.pyc" % i), doraise=True)


def git(*args):
    return subprocess.run(["git", "-C", str(REPO)] + list(args), capture_output=True, text=True)


class RepositoryTests(unittest.TestCase):
    """What this public repository may hold: no dumps, no password files, no
    local choice of database and no connection string with a password."""

    def test_git_ignores_the_venv_local_settings_dumps_and_pgpass(self):
        for path in ("admin/.venv/bin/python", "admin/local/store.json", "bgs_corner-20260914-120000.dump",
                     "admin/tests/x.dump", ".pgpass", "admin/.pgpass"):
            self.assertEqual(git("check-ignore", "-q", "--no-index", path).returncode, 0, path)

    def test_nothing_secret_is_tracked(self):
        tracked = git("ls-files", "-z").stdout.split("\0")
        bad = [p for p in tracked if p.endswith(".dump") or p.split("/")[-1] in (".pgpass", ".env")
               or p.startswith(("admin/local/", "admin/.venv/"))]
        self.assertEqual(bad, [])
        for rx in (r"postgres(ql)?://[^[:space:]/:@]+:[^@[:space:]]+@", r"\bpassword[[:space:]]*="):
            found = git("grep", "-n", "-I", "-i", "-E", rx)
            self.assertEqual(found.returncode, 1, found.stdout[:2000])   # 1: no line matches


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class ExitNetTests(unittest.TestCase):
    """However a test run ends, the admin server its Box started stops and
    the clone goes (cleanup.py). Each test starts a Box in a child run on
    ADMIN_PLUMBING_BOX_PORT and ends that run."""

    def run_box(self, end):
        p = subprocess.Popen([sys.executable, "-c", BOX_RUN % {"tests": str(TESTS), "port": BOX_PORT, "end": end}],
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        line = p.stdout.readline().split()
        if len(line) != 2:
            p.kill()
            p.wait(10)
            self.fail("the child run did not start its Box: %s" % p.stderr.read())
        return p, int(line[0]), pathlib.Path(line[1])

    def gone(self, pid, tmp, seconds):
        for _ in range(seconds * 10):
            if not alive(pid) and not tmp.exists():
                return True
            time.sleep(0.1)
        return False

    def test_a_run_that_dies_of_the_alarm_stops_its_server(self):
        # SIGALRM is what the 110 s limit on a test command sends, and Python
        # dies of it without running atexit
        p, pid, tmp = self.run_box("signal.alarm(1)")
        p.wait(60)
        self.assertEqual(p.returncode, -signal.SIGALRM, p.stderr.read())
        self.assertTrue(self.gone(pid, tmp, 2))

    def test_a_killed_run_stops_its_server(self):
        # nothing catches SIGKILL: the Box's watchdog stops the server
        p, pid, tmp = self.run_box("os.kill(os.getpid(), signal.SIGKILL)")
        p.wait(60)
        self.assertEqual(p.returncode, -signal.SIGKILL)
        self.assertTrue(self.gone(pid, tmp, 15))


if __name__ == "__main__":
    unittest.main()
