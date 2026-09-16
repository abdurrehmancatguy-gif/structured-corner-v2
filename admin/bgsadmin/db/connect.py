"""Connections to the admin's database, and the checks each one passes
before it is used.

A DSN names everything itself: host (the absolute folder of the server's
unix socket), port, dbname and user. Nothing falls back to libpq's defaults
or to the environment: test servers start from clones that inherit it, and
must never reach the owner's database. A DSN never holds a password: the
owner's server trusts its local socket, and a password belongs in ~/.pgpass
(chmod 600), not in a command line or a repository file.

Every connection has the same limits: 5 s to connect, 15 s per statement,
5 s waiting for a lock, and 10 minutes idle inside a transaction, which must
outlive the derivatives (300 s), the favicon (60 s) and the build (60 s) that
a save runs while its transaction is open.

The admin's advisory locks in its database, (LOCK_CLASS, n):
    ADMIN (1)  one admin, or one dbtool migrate, per database, for its life
    SAVE (2)   a save's transaction; verify waits on it, shared
"""
import collections

import psycopg
from psycopg import conninfo

from ..store.base import CannotStart

LOCK_CLASS = 16967
ADMIN = 1
SAVE = 2
TIMEOUTS = "-c statement_timeout=15000 -c lock_timeout=5000 -c idle_in_transaction_session_timeout=600000"
NEEDS = ("host", "port", "dbname", "user")
OLDEST = 150000                    # server_version_num: PostgreSQL 15
START = "brew services start postgresql@18"
PASSWORD = ("The DSN holds a password. Keep passwords out of commands and repo files: use ~/.pgpass "
            "(chmod 600), which libpq reads by itself.")

Identity = collections.namedtuple("Identity", "user dbname superuser version_num version encoding owner")


def _first(e):
    lines = [l.strip() for l in str(e).strip().splitlines() if l.strip()]
    return lines[0] if lines else e.__class__.__name__


def check_dsn(dsn):
    """The DSN's parts as a dict, or CannotStart (2) before any connection
    is tried."""
    if not isinstance(dsn, str) or not dsn.strip():
        raise CannotStart('No database was named. Give a DSN such as '
                          '"host=/tmp port=5432 dbname=bgs_corner user=bgs_corner_app".')
    try:
        params = conninfo.conninfo_to_dict(dsn)
    except psycopg.Error as e:
        raise CannotStart("That is not a connection string libpq can read (%s)." % _first(e))
    if "password" in params:
        raise CannotStart(PASSWORD)
    missing = [k for k in NEEDS if not str(params.get(k) or "").strip()]
    if missing:
        raise CannotStart("The DSN must name its own %s, so nothing is taken from libpq's defaults or the "
                          "environment." % " and ".join(missing))
    if params.get("hostaddr") or params.get("service"):
        raise CannotStart("The DSN may not use hostaddr or service: name the server's socket folder as host.")
    host, port = str(params["host"]), str(params["port"])
    if "," in host or not host.startswith("/"):
        raise CannotStart("The DSN's host must be the folder of the server's unix socket, an absolute path such "
                          "as /tmp: the admin only talks to the server on its own computer.")
    if not (port.isascii() and port.isdigit()):
        raise CannotStart("The DSN's port must be one number, such as 5432.")
    return params


def where(params):
    return "%s port %s" % (params["host"], params["port"])


def connect(dsn, autocommit=False, app="bgs-admin", read_only=False):
    """A connection with the admin's limits. Raises psycopg's
    OperationalError when there is no server to talk to."""
    options = TIMEOUTS + (" -c default_transaction_read_only=on" if read_only else "")
    return psycopg.connect(dsn, autocommit=autocommit, connect_timeout=5, application_name=app, options=options)


def not_answering(params, e):
    """The CannotStart for a failed connection: 2 when the server answered
    with a refusal (no such database or role, no right to connect), 3 when
    nothing answered."""
    text = str(e)
    if "FATAL:" in text:
        reason = text.split("FATAL:", 1)[1].strip().splitlines()[0].strip()
        return CannotStart("The database server at %s refused the connection: %s." % (where(params), reason), 2)
    reason = _first(e)
    if "failed: " in reason:
        reason = reason.split("failed: ", 1)[1].strip()
    return CannotStart("PostgreSQL is not answering at %s (%s). Start it with: %s." % (where(params), reason, START), 3)


def open_checked(dsn, params, autocommit=False, app="bgs-admin", read_only=False):
    """connect(), with a failure turned into CannotStart."""
    try:
        return connect(dsn, autocommit=autocommit, app=app, read_only=read_only)
    except psycopg.OperationalError as e:
        raise not_answering(params, e)


def identity(conn):
    row = conn.execute(
        "SELECT current_user, current_database(), r.rolsuper, current_setting('server_version_num')::integer, "
        "current_setting('server_version'), pg_encoding_to_char(d.encoding), d.datdba = r.oid "
        "FROM pg_roles AS r, pg_database AS d "
        "WHERE r.rolname = current_user AND d.datname = current_database()").fetchone()
    return Identity(*row)


def check_identity(conn, params):
    """Who this connection is, or CannotStart (2): never a superuser, the
    database the DSN names, PostgreSQL 15 or newer, UTF8."""
    ident = identity(conn)
    if ident.superuser:
        raise CannotStart("Connected as %s, a superuser. Use user=bgs_corner_app (or bgs_corner, the database's "
                          "owner), so the admin cannot touch the server's other databases." % ident.user)
    if ident.dbname != params["dbname"]:
        raise CannotStart("Connected to the database %s, not %s." % (ident.dbname, params["dbname"]))
    if ident.version_num < OLDEST:
        raise CannotStart("PostgreSQL %s is older than 15, which the admin needs." % ident.version)
    if ident.encoding != "UTF8":
        raise CannotStart("The database %s is %s, not UTF8." % (ident.dbname, ident.encoding))
    return ident


def app_role_exists(conn, role="bgs_corner_app"):
    return bool(conn.execute("SELECT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s)", (role,)).fetchone()[0])


def with_user(params, user):
    """The same DSN for another role."""
    out = dict(params, user=user)
    return " ".join("%s=%s" % (k, _quote(out[k])) for k in NEEDS) + "".join(
        " %s=%s" % (k, _quote(v)) for k, v in out.items() if k not in NEEDS)


def _quote(v):
    v = str(v)
    if v and all(c.isalnum() or c in "/._-" for c in v):
        return v
    return "'%s'" % v.replace("\\", "\\\\").replace("'", "\\'")
