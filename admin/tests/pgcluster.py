"""Throwaway PostgreSQL clusters for the admin's tests.

    import pgcluster
    c = pgcluster.cluster()               # this test process's cluster, started on first use
    dsn = c.new_database("box_4731_0")    # a fresh database owned by bgs_corner
    c.psql("SELECT 1", dbname="box_4731_0")
    c.drop_database("box_4731_0")

Each cluster is initdb'd into a private folder of its own, with its unix
socket in that same folder and no TCP at all (listen_addresses=''), trust
auth and fsync off. It never reaches the owner's shared server: every libpq
variable (PGHOST, PGPORT and the rest) is dropped from the environment of the
tools it runs and of the admin servers Box starts, and every DSN it hands out
names its own folder.

Where: in ADMIN_PG_ROOT, else the system's temporary folder. macOS allows a
unix socket path of 103 bytes at most, and the socket sits in the cluster's
folder, so the folder is named as short as the root needs: bgspg-<random>,
or two characters under a long root. A root too long even for that is
refused with a message.

ADMIN_PG_PORT (5453 by default) only names the socket file: there is no TCP,
so two clusters on one port in two folders do not meet. ADMIN_PG_BIN is
where initdb, pg_ctl and psql are (/opt/homebrew/bin).

However the test run ends, the cluster stops and its folder goes (cleanup.py:
atexit, the SIGTERM, SIGHUP and SIGALRM handler, and a watchdog for SIGKILL).
A folder whose run ended without cleaning up (a reboot, say) is swept when
the next cluster starts. The harness needs no database driver: it talks to
the cluster through psql, so it runs under /usr/bin/python3 as well.
"""
import itertools
import os
import pathlib
import re
import shutil
import subprocess
import tempfile
import time

import cleanup

BIN = pathlib.Path(os.environ.get("ADMIN_PG_BIN", "/opt/homebrew/bin"))
PORT = int(os.environ.get("ADMIN_PG_PORT", "5453"))
ROOT = os.environ.get("ADMIN_PG_ROOT") or tempfile.gettempdir()
PREFIX = "bgspg-"
MARK = ".bgspg-cluster"      # in every cluster folder: what sweep() may remove
SOCKET_MAX = 103             # sun_path is 104 bytes on macOS, NUL included: 103 binds, 104 does not
NAME = re.compile(r"[a-z][a-z0-9_]{0,62}")

# The roles the owner's server has, made as the build plan's owner commands
# make them: the admin must work as roles that are not superusers and cannot
# create databases or roles.
OWNER_ROLE = "CREATE ROLE bgs_corner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
APP_ROLE = ("CREATE ROLE bgs_corner_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS "
            "CONNECTION LIMIT 10")

# What the watchdog runs once the test process is gone: $1 pg_ctl, $2 the
# data folder, $3 the cluster's folder.
STOP = '"$1" -D "$2" -m immediate -s stop >/dev/null 2>&1; rm -rf "$3"'

_cluster = None


def clean_env():
    """This environment without any libpq variable, so nothing started with
    it can fall back to the shared server."""
    return {k: v for k, v in os.environ.items() if not k.startswith("PG")}


def tool_env():
    """For initdb, pg_ctl, psql, pg_dump and pg_restore: a clean environment
    in the C locale. Without LC_ALL, PostgreSQL 18 on macOS can stop at start
    with 'postmaster became multithreaded during startup'."""
    return dict(clean_env(), LC_ALL="C", LANG="C")


def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def sweep(root=None):
    """Stop and remove the clusters in root whose test run is gone. Only
    folders holding MARK are looked at."""
    base = pathlib.Path(root or ROOT)
    for d in (base.iterdir() if base.is_dir() else ()):
        if not (d / MARK).is_file():
            continue
        try:
            pid = int((d / "owner.pid").read_text())
        except (OSError, ValueError):
            continue
        if _alive(pid):
            continue
        if (d / "data" / "postmaster.pid").exists():
            subprocess.run([str(BIN / "pg_ctl"), "-D", str(d / "data"), "-m", "immediate", "-s", "stop"],
                           env=tool_env(), capture_output=True, timeout=30)
        shutil.rmtree(str(d), ignore_errors=True)


def _new_root(base, port):
    """A new private folder for one cluster in base, named as short as the
    socket path needs."""
    base = pathlib.Path(base)
    tail = len("/.s.PGSQL.%d" % port)
    if len(str(base)) + 1 + len(PREFIX) + 8 + tail <= SOCKET_MAX:
        return pathlib.Path(tempfile.mkdtemp(prefix=PREFIX, dir=str(base)))
    if len(str(base)) + 3 + tail > SOCKET_MAX:
        raise RuntimeError("%s is too long for the folder of a unix socket (macOS allows %d bytes for the whole "
                           "path). Set ADMIN_PG_ROOT to a shorter folder." % (base, SOCKET_MAX))
    letters, chars = "abcdefghijklmnopqrstuvwxyz", "abcdefghijklmnopqrstuvwxyz0123456789"
    for a, b in itertools.product(letters, chars):
        d = base / (a + b)
        try:
            d.mkdir(mode=0o700)
            return d
        except FileExistsError:
            continue
    raise RuntimeError("No free two-character folder name is left in %s." % base)


class Cluster:
    def __init__(self, port=PORT, root=None):
        self.port = int(port)
        self.root = _new_root(root or ROOT, self.port)
        self.data = self.root / "data"
        self.sock = self.root
        self.timings = {}
        self._watch = None
        cleanup.on_exit(self.stop)
        (self.root / "owner.pid").write_text(str(os.getpid()))
        (self.root / MARK).write_text("A throwaway PostgreSQL cluster of the admin's tests (admin/tests/pgcluster.py).\n")

    @property
    def socket(self):
        return self.sock / (".s.PGSQL.%d" % self.port)

    def _tool(self, *args, timeout=60):
        return subprocess.run([str(BIN / args[0])] + [str(a) for a in args[1:]], env=tool_env(),
                              capture_output=True, text=True, timeout=timeout)

    def start(self, app_role=True):
        """initdb, start, and the owner's role; the admin's own role too
        unless app_role is False (the admin must work without it)."""
        t = time.monotonic()
        p = self._tool("initdb", "-D", self.data, "-A", "trust", "-U", "postgres", "-E", "UTF8",
                       "--locale=C", "--no-sync", "--no-instructions")
        if p.returncode:
            raise RuntimeError("initdb failed: %s" % p.stderr[-2000:])
        self.timings["initdb"] = time.monotonic() - t
        self._watch = cleanup.watchdog("/bin/sh", "-c", STOP, "bgspg-stop", BIN / "pg_ctl", self.data, self.root)
        opts = ("-k %s -p %d -c listen_addresses='' -c unix_socket_permissions=0700 -c fsync=off "
                "-c synchronous_commit=off -c full_page_writes=off -c max_connections=50" % (self.sock, self.port))
        t = time.monotonic()
        p = self._tool("pg_ctl", "-D", self.data, "-l", self.root / "server.log", "-w", "-t", "30", "-o", opts, "start")
        if p.returncode:
            log = self.root / "server.log"
            raise RuntimeError("The test cluster did not start: %s %s" % (
                p.stderr[-1000:], log.read_text(errors="replace")[-2000:] if log.exists() else ""))
        self.timings["start"] = time.monotonic() - t
        self.psql(OWNER_ROLE)
        if app_role:
            self.psql(APP_ROLE)
        return self

    def dsn(self, dbname="bgs_corner", user="bgs_corner"):
        """A libpq connection string for this cluster's own socket."""
        return "host=%s port=%d dbname=%s user=%s" % (self.sock, self.port, dbname, user)

    def psql(self, sql, dbname="postgres", user="postgres"):
        """Run SQL as the cluster's superuser (or another role) through psql;
        returns the unaligned, tuples-only output."""
        p = self._tool("psql", "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-h", self.sock, "-p", self.port,
                       "-U", user, "-d", dbname, "-c", sql)
        if p.returncode:
            raise RuntimeError("psql failed: %s" % p.stderr.strip())
        return p.stdout

    def new_database(self, name):
        """A database made the way the owner's bgs_corner was: owned by
        bgs_corner, CONNECT taken away from PUBLIC. Returns its DSN."""
        if not NAME.fullmatch(name):
            raise ValueError("Not a database name for a test: %r" % (name,))
        self.psql("CREATE DATABASE %s OWNER bgs_corner TEMPLATE template0 ENCODING 'UTF8' LOCALE 'C'" % name)
        self.psql("REVOKE CONNECT ON DATABASE %s FROM PUBLIC" % name)
        return self.dsn(name)

    def drop_database(self, name):
        if not NAME.fullmatch(name):
            raise ValueError("Not a database name for a test: %r" % (name,))
        self.psql("DROP DATABASE IF EXISTS %s WITH (FORCE)" % name)

    def stop(self):
        cleanup.forget(self.stop)
        t = time.monotonic()
        if (self.data / "postmaster.pid").exists():
            p = self._tool("pg_ctl", "-D", self.data, "-m", "fast", "-w", "-t", "20", "-s", "stop", timeout=30)
            if p.returncode:
                self._tool("pg_ctl", "-D", self.data, "-m", "immediate", "-s", "stop", timeout=30)
        self.timings["stop"] = time.monotonic() - t
        cleanup.stop(self._watch)
        self._watch = None
        shutil.rmtree(str(self.root), ignore_errors=True)


def cluster():
    """The one cluster of this test process, started on first use."""
    global _cluster
    if _cluster is None:
        sweep()
        _cluster = Cluster().start()
    return _cluster
