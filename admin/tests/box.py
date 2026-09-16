"""A temporary clone of the repository with the admin server running on it.

Every test module starts its own Box on its own port (4700 to 4799; 4310 is
the owner's preview), so modules can run side by side:

    from box import Box
    b = Box(4741)
    status, body = b.api("GET", "products")

The clone gets this working tree's flow/ copied over it, so tests exercise
uncommitted changes to build.py, shop.js and content as well; the admin code
always runs from this working tree. The server runs with --no-push, always,
and with an environment that holds no libpq variable (pgcluster.clean_env),
so nothing it starts can reach the owner's database.

ADMIN_TEST_STORE says which store the servers run on, for the tests only (no
server reads it): json, the default, or postgres. In PostgreSQL mode each Box
gets a database of its own on this test process's throwaway cluster
(pgcluster.py), and the owner's own command makes it: dbtool migrate --apply
on the clone, which also writes the clone's admin/local/store.json. The
server then starts with no store flags, as the owner's does. PostgreSQL mode
needs psycopg, so its test runs use the admin's virtualenv, whose interpreter
also runs dbtool and the servers.

However a test run ends (a failure, the 110 s alarm, a kill), the server is
stopped and the clone removed: every Box is on cleanup.py's exit nets from
the start, and a watchdog stops its server even after a SIGKILL.
"""
import contextlib
import http.client
import importlib.util
import itertools
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

import cleanup
import pgcluster

ADMIN = pathlib.Path(__file__).resolve().parent.parent
REPO = ADMIN.parent
STORE = os.environ.get("ADMIN_TEST_STORE", "json")
_seq = itertools.count()        # test_bulk_ui makes a Box per test on one port: a new database each time

# What a Box's watchdog runs once the test process is gone: $1 the server's
# pid, $2 the Box's folder. The server is stopped only if that pid is still
# this Box's server (its command line names the folder); then the folder goes.
SERVER_WATCH = ('alive() { case "$(ps -o command= -p "$1" 2>/dev/null)" in *"$2"*) return 0;; esac; return 1; }; '
                'if alive "$1" "$2"; then kill "$1"; sleep 2; if alive "$1" "$2"; then kill -9 "$1"; fi; fi; '
                'rm -rf "$2"')


def _skip(_dir, names):
    return {n for n in names if n in (".backups", "__pycache__") or (n.startswith(".") and n.endswith(".tmp"))}


class Box:
    def __init__(self, port, overlay=True, args=()):
        self._clone(port)
        if overlay:
            shutil.copytree(str(REPO / "flow"), str(self.repo / "flow"), dirs_exist_ok=True, ignore=_skip)
        self._start(args)

    def _clone(self, port, prefix="bgsadmin-"):
        """A temporary folder with a clone of this repository in it (repo/),
        on the exit nets from the start, so it goes however the run ends."""
        self.port = int(port)
        self.store = STORE
        self.cluster = None
        self.db = None
        self.proc = None
        self._watch = None
        self.tmp = tempfile.mkdtemp(prefix=prefix)
        cleanup.on_exit(self._kill)
        self.repo = pathlib.Path(self.tmp) / "repo"
        subprocess.run(["git", "clone", "-q", str(REPO), str(self.repo)], check=True)

    def _store(self, env):
        """The interpreter, the extra server arguments and the environment for
        this Box's store. The JSON store: this interpreter, as it is."""
        if self.store == "json":
            return sys.executable, [], env
        if self.store != "postgres":
            raise RuntimeError("ADMIN_TEST_STORE=%r: json or postgres." % (self.store,))
        if importlib.util.find_spec("psycopg") is None:
            raise RuntimeError("ADMIN_TEST_STORE=postgres needs psycopg: run the tests with admin/.venv/bin/python.")
        self.cluster = pgcluster.cluster()
        self.db = "box_%d_%d" % (self.port, next(_seq))
        dsn = self.cluster.new_database(self.db)
        p = subprocess.run([sys.executable, str(ADMIN / "dbtool.py"), "migrate", "--apply", "--dsn", dsn,
                            "--repo", str(self.repo)], env=env, capture_output=True, text=True, timeout=100)
        if p.returncode != 0:
            raise RuntimeError("dbtool migrate --apply did not make the Box's database: %s%s"
                               % (p.stdout[-3000:], p.stderr[-2000:]))
        return sys.executable, [], env

    def _start(self, args=()):
        py, extra, env = self._store(pgcluster.clean_env())
        self._spawn(py, list(extra) + list(args), env)

    def _spawn(self, py, extra, env):
        """Start the admin server on the clone and wait until it answers."""
        self.proc = subprocess.Popen([str(py), str(ADMIN / "server.py"), "--port", str(self.port),
                                      "--repo", str(self.repo), "--no-push"] + list(extra),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
        self._watch = cleanup.watchdog("/bin/sh", "-c", SERVER_WATCH, "bgs-box", self.proc.pid, self.tmp)
        up = False
        for _ in range(150):
            if self.proc.poll() is not None:
                break
            try:
                if self.raw("GET", "/")[0] == 200:
                    up = True
                    break
            except OSError:
                pass
            time.sleep(0.1)
        if not up:
            if self.proc.poll() is None:
                self.proc.terminate()
            out = self.proc.stdout.read(4000).decode("utf-8", "replace")
            self.close()
            raise RuntimeError("the admin server did not start: %s" % out)
        st, _, body = self.raw("GET", "/admin/", headers={"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "none"})
        self.token = re.search(rb'name="admin-token" content="([^"]+)"', body).group(1).decode()

    def raw(self, method, path, body=None, headers=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=100)
        h = {"Host": host if host is not None else "localhost:%d" % self.port}
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def api(self, method, path, body=None, rev=None, token=True, origin=True, ctype="application/json", headers=None):
        """JSON in and out. bytes are sent as they are, typed with ctype, which
        is how an upload is sent."""
        h = {}
        if token:
            h["X-Admin-Token"] = self.token
        if origin and method not in ("GET", "HEAD"):
            h["Origin"] = "http://localhost:%d" % self.port
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            h["Content-Type"] = ctype
        if rev:
            h["If-Match"] = '"%s"' % rev
        h.update(headers or {})
        st, hd, raw = self.raw(method, "/admin/api/v1/" + path, data, h)
        try:
            return st, (json.loads(raw) if raw else None)
        except ValueError:
            return st, raw

    def content(self, name):
        return json.loads((self.repo / "flow" / "content" / ("%s.json" % name)).read_text(encoding="utf-8"))

    def _kill(self):
        """Stop the server and remove the folder: close() and the exit nets."""
        if self.proc is not None:
            if self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(10)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
                    self.proc.wait(5)
            if self.proc.stdout:
                self.proc.stdout.close()
        cleanup.stop(self._watch)
        self._watch = None
        if self.db is not None:
            # on the exit nets the cluster may be gone already, and the database with it
            with contextlib.suppress(Exception):
                self.cluster.drop_database(self.db)
            self.db = None
        shutil.rmtree(self.tmp, ignore_errors=True)

    def close(self):
        cleanup.forget(self._kill)
        self._kill()
