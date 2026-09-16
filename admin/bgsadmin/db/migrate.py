"""The runner for the numbered migrations in migrations/ (NNN_name.sql).

Each file is applied once, in order, by the database's owner, in the same
transaction as its bgs.schema_migrations row (version, name, sha256 and the
OS user), and every run ends by granting the admin's own role its rights
(bgs.grant_app_role(), which does nothing until that role exists). An
applied migration is never edited: the runner refuses a database whose
applied files no longer match this checkout's, and one whose schema is newer
than this checkout knows. Every change is a new file.

A fresh database is also bound to one checkout (bgs.store_meta): the admin
and dbtool refuse any other, so a test clone can never export from or into
the owner's database.
"""
import collections
import hashlib
import pathlib
import re

from ..store.base import CannotStart

FOLDER = pathlib.Path(__file__).resolve().parent / "migrations"
FILE = re.compile(r"(?P<version>[0-9]{3})_[a-z0-9_]+\.sql")
APP = "bgs-corner-admin"
RUN = "admin/.venv/bin/python admin/dbtool.py migrate"

Migration = collections.namedtuple("Migration", "version name path sha")


def available(folder=FOLDER):
    """This checkout's migrations, in order, numbered 001 on without gaps."""
    out = []
    for p in sorted(pathlib.Path(folder).iterdir()):
        if p.suffix != ".sql":
            continue
        m = FILE.fullmatch(p.name)
        if not m:
            raise CannotStart("%s is not named like a migration (NNN_name.sql)." % p.name)
        out.append(Migration(int(m.group("version")), p.name, p, hashlib.sha256(p.read_bytes()).hexdigest()))
    for i, m in enumerate(out, 1):
        if m.version != i:
            raise CannotStart("The migrations must be numbered 001, 002 and so on without gaps: %s is out of "
                              "place." % m.name)
    return out


def installed(cur):
    """Whether the admin's schema is in this database at all."""
    return bool(cur.execute("SELECT to_regclass('bgs.schema_migrations') IS NOT NULL").fetchone()[0])


def applied(cur):
    """[(version, name, sha256)] of what the database has, oldest first."""
    if not installed(cur):
        return []
    return [tuple(r) for r in cur.execute(
        "SELECT version, name, sha256 FROM bgs.schema_migrations ORDER BY version").fetchall()]


def pending(cur, folder=FOLDER):
    """The migrations this database still needs, once the ones it has are
    found to be exactly this checkout's files."""
    files = available(folder)
    by_version = {m.version: m for m in files}
    done = applied(cur)
    for version, name, digest in done:
        m = by_version.get(version)
        if m is None:
            raise CannotStart("The database's schema is newer than this checkout: it has migration %s, which this "
                              "checkout does not. Update the checkout first." % name)
        if (m.name, m.sha) != (name, digest):
            raise CannotStart("%s is not the migration the database applied as %s: an applied migration was "
                              "edited. Put the file back as it was, and make every change a new migration."
                              % (m.name, name))
    have = {v for v, _, _ in done}
    return [m for m in files if m.version not in have]


def foreign_tables(cur):
    """Tables, views and sequences in this database that are not the
    admin's. With no bgs.store_meta, any of them means the DSN names someone
    else's database."""
    return [r[0] for r in cur.execute(
        "SELECT n.nspname || '.' || c.relname FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace "
        "WHERE c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S') AND n.nspname <> 'bgs' "
        "AND n.nspname NOT IN ('pg_catalog', 'information_schema') AND n.nspname !~ '^pg_(toast|temp)' "
        "ORDER BY 1").fetchall()]


def bound_to(cur):
    """The checkout this database belongs to, or None before the first apply."""
    if cur.execute("SELECT to_regclass('bgs.store_meta') IS NULL").fetchone()[0]:
        return None
    row = cur.execute("SELECT repo_path FROM bgs.store_meta").fetchone()
    return row[0] if row else None


def check_binding(cur, repo):
    """CannotStart unless the database is unbound or bound to repo."""
    bound = bound_to(cur)
    if bound is not None and bound != str(repo):
        raise CannotStart("The database belongs to the checkout %s, not %s. The admin only exports into the "
                          "checkout the database was migrated from." % (bound, repo))
    return bound


def check_fresh_or_ours(cur):
    """CannotStart when the database holds tables but not the admin's: a
    DSN that names another database by mistake."""
    if bound_to(cur) is None:
        other = foreign_tables(cur)
        if other:
            raise CannotStart("The database already holds tables that are not the admin's (%s%s). Check the DSN's "
                              "dbname: the admin makes its tables only in an empty database or in its own."
                              % (", ".join(other[:5]), " and more" if len(other) > 5 else ""))


def apply(cur, repo, actor, folder=FOLDER):
    """Apply what is pending and bind a fresh database to repo, in the
    caller's transaction (nothing is committed here). Returns the names
    applied."""
    todo = pending(cur, folder)
    for m in todo:
        cur.execute(m.path.read_text(encoding="utf-8"))
        cur.execute("INSERT INTO bgs.schema_migrations (version, name, sha256, applied_by) VALUES (%s, %s, %s, %s)",
                    (m.version, m.name, m.sha, actor))
    if bound_to(cur) is None:
        cur.execute("INSERT INTO bgs.store_meta (app, repo_path, bound_by) VALUES (%s, %s, %s)",
                    (APP, str(repo), actor))
    cur.execute("SELECT bgs.grant_app_role()")
    return [m.name for m in todo]


def check_current(cur, repo, folder=FOLDER):
    """What the admin checks at start: the schema is exactly this checkout's
    migrations, and the database is bound to this checkout."""
    if not installed(cur):
        raise CannotStart("The database has no admin tables yet. Run %s --dsn \"<the owner's DSN>\" (a dry run), "
                          "then the same line with --apply." % RUN)
    todo = pending(cur, folder)
    if todo:
        raise CannotStart("The database needs %s first. Stop the admin and run %s --dsn \"<the owner's DSN>\" "
                          "--apply." % (", ".join(m.name for m in todo), RUN))
    bound = check_binding(cur, repo)
    if bound is None:
        raise CannotStart("The database belongs to no checkout yet. Run %s --apply from this checkout." % RUN)
