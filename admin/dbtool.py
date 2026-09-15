#!/usr/bin/env python3
"""The owner's tool for the admin's PostgreSQL database.

    admin/.venv/bin/python admin/dbtool.py migrate --dsn "host=/tmp port=5432 dbname=bgs_corner user=bgs_corner"
    admin/.venv/bin/python admin/dbtool.py migrate --dsn "..." --apply
    admin/.venv/bin/python admin/dbtool.py verify
    admin/.venv/bin/python admin/dbtool.py use json

migrate  applies the migrations this checkout has and the database lacks and,
         into an empty database, loads flow/content. On the way it proves that
         the database gives the same data back and that the site builds from
         its export to the same files. Everything happens in one transaction,
         which a dry run (no --apply) always rolls back. --apply also switches
         this checkout to the database (admin/local/store.json), as the
         admin's own role bgs_corner_app when it exists. Run it as the
         database's owner, with the admin stopped.
verify   read-only, safe while the admin runs: the schema, the checkout it
         belongs to, the database's checks and triggers, the admin role's
         rights, and each content file against the database's export.
use      json or postgres: the store this checkout's admin starts on.

Exit status: 0 done (or nothing to do), 1 differences found or rows refused,
2 refused to run, 3 the database is not answering. It needs psycopg, which
the admin's virtualenv has (admin/requirements.txt). A DSN names host (the
server's socket folder), port, dbname and user, and never a password.
"""
import argparse
import contextlib
import fcntl
import getpass
import pathlib
import shutil
import sys
import tempfile
import time

ADMIN = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ADMIN))

from bgsadmin import config, tools                       # noqa: E402
from bgsadmin.errors import ApiError                     # noqa: E402
from bgsadmin.jsonutil import canonical, strict_loads    # noqa: E402
from bgsadmin.store import files                         # noqa: E402
from bgsadmin.store.base import CannotStart, content_names, rev_of, sha  # noqa: E402

VENV = ("dbtool needs psycopg, which the admin's virtualenv has: run it as admin/.venv/bin/python "
        "admin/dbtool.py (admin/requirements.txt says how that virtualenv is made).")


def say(*lines):
    for line in lines:
        print(line)
    sys.stdout.flush()


@contextlib.contextmanager
def admin_lock(cfg):
    """The lock every admin on this checkout holds: dbtool runs only while
    no admin does, and no admin starts while it runs."""
    cfg.backups.mkdir(parents=True, exist_ok=True)
    f = open(str(cfg.backups / ".admin.lock"), "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        raise CannotStart("An admin is running on %s. Stop it first." % cfg.repo)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(f, fcntl.LOCK_UN)
        f.close()


def no_journals(cfg):
    left = [d.name for d, _ in files.journals(cfg)]
    if left:
        raise CannotStart("A save was cut short in this checkout (%s). Start the admin once so it settles it, stop "
                          "it, then run this again." % ", ".join(left))


def parse_all(snapshot):
    """{name: data} from the files' bytes, parsed as strictly as a request
    body; the names that fail, with why."""
    out, bad = {}, []
    for name, raw in snapshot.items():
        try:
            out[name] = strict_loads(raw)
        except ApiError as e:
            bad.append("%s.json: %s" % (name, e.details or e.message))
    return out, bad


def _skip(_dir, names):
    return {n for n in names if n in (".backups", "__pycache__") or (n.startswith(".") and n.endswith(".tmp"))}


def clean_room(cfg, exports):
    """Build the site from exports ({name: bytes}) in a copy of flow/ and
    compare every file build.py and make_derivatives write with this
    checkout's. Returns (files compared, problems)."""
    tmp = tempfile.mkdtemp(prefix="bgs-migrate-")
    try:
        flow = pathlib.Path(tmp) / "flow"
        shutil.copytree(str(cfg.flow), str(flow), ignore=_skip)
        for name, data in exports.items():
            (flow / "content" / ("%s.json" % name)).write_bytes(data)
        build = tools.run(cfg, "build", cwd=flow)
        if not build["ok"]:
            return 0, ["build.py stopped on the database's export: %s" % "; ".join(build["problems"])]
        gen = cfg.generated_files()
        problems = []
        for p in gen:
            rel = p.relative_to(cfg.flow)
            mine = p.read_bytes() if p.exists() else None
            theirs = (flow / rel).read_bytes() if (flow / rel).exists() else None
            if mine != theirs:
                problems.append("flow/%s differs when the site is built from the database's export" % rel)
        return len(gen), problems
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="The admin's PostgreSQL database: migrate, verify and use.")
    sub = ap.add_subparsers(dest="cmd", metavar="migrate|verify|use")
    sub.required = True
    m = sub.add_parser("migrate", help="apply the migrations and, into an empty database, load flow/content")
    m.add_argument("--dsn", required=True, help="the owner's DSN: host=<socket folder> port=... dbname=... user=...")
    m.add_argument("--apply", action="store_true",
                   help="commit, and switch this checkout to the database; without it everything is rolled back")
    v = sub.add_parser("verify", help="read-only: does the database agree with the files and itself")
    v.add_argument("--dsn", help="host=<socket folder> port=... dbname=... user=... (this checkout's own by default)")
    u = sub.add_parser("use", help="choose the store this checkout's admin starts on")
    u.add_argument("store", choices=config.STORES)
    u.add_argument("--dsn", help="for postgres: the admin's DSN (the one this checkout already has by default)")
    for p in (m, v, u):
        p.add_argument("--repo", help="the checkout (the one dbtool lives in by default)")
    args = ap.parse_args(argv)
    repo = pathlib.Path(args.repo).resolve() if args.repo else ADMIN.parent
    cfg = config.Config(repo)
    try:
        if not cfg.content.is_dir():
            raise CannotStart("No flow/content in %s." % repo)
        try:
            import psycopg  # noqa: F401
        except ImportError:
            raise CannotStart(VENV)
        return COMMANDS[args.cmd](cfg, args)
    except CannotStart as e:
        print(e.message, file=sys.stderr)
        return e.status


# ---- migrate ------------------------------------------------------------------------

COUNTS = ("SELECT (SELECT count(*) FROM bgs.products), (SELECT count(*) FROM bgs.documents), "
          "(SELECT count(*) FROM bgs.revisions), (SELECT count(*) FROM bgs.product_refs), "
          "(SELECT count(*) FROM bgs.audit_log)")


def rows_line(cur):
    return ("rows        %d products, %d documents, %d revisions, %d product references; audit log %d"
            % tuple(cur.execute(COUNTS).fetchone()))


def target_lines(cfg, ident, params):
    from bgsadmin.db import connect
    return ("database    %s as %s at %s (PostgreSQL %s)" % (ident.dbname, ident.user, connect.where(params),
                                                             ident.version),
            "checkout    %s" % cfg.repo)


def sentences(name, db, disk):
    """diff.py's sentences for what the file holds that the database does not."""
    from bgsadmin import diff, schema
    try:
        fields = schema.load()[name]["fields"]
        ctx = {"products": disk if name == "products" else {}}
        entries = (diff.products(fields, db, disk, ctx) if name == "products"
                   else diff.document(fields, db, disk, ctx))
        return [e["text"] for e in entries] or ["the same data in another key order"]
    except Exception:
        return ["differs from the database"]


def switch(cfg, conn, params):
    """Point this checkout's admin at the database: admin/local/store.json,
    as the admin's own role when it exists, else as the owner."""
    from bgsadmin.db import connect
    role = APP_ROLE if connect.app_role_exists(conn, APP_ROLE) else params["user"]
    config.write_store_choice(cfg.repo, "postgres", connect.with_user(params, role))
    line = "switched    this checkout's admin starts on the database now, as %s (admin/local/store.json)" % role
    if role != APP_ROLE:
        line += ("; create %s (README, Database) and run this again, so the admin runs with only the rights it "
                 "needs" % APP_ROLE)
    return line


def migrate(cfg, args):
    from bgsadmin.db import connect
    params = connect.check_dsn(args.dsn)
    t0 = time.monotonic()
    with admin_lock(cfg):
        no_journals(cfg)
        conn = connect.open_checked(args.dsn, params, autocommit=True, app="bgs-dbtool")
        try:
            ident = connect.check_identity(conn, params)
            if not ident.owner:
                raise CannotStart("Migrations run as the database's owner, and %s does not own %s. Use the owner's "
                                  "role (user=bgs_corner)." % (ident.user, ident.dbname))
            if not conn.execute("SELECT pg_try_advisory_lock(%s, %s)",
                                (connect.LOCK_CLASS, connect.ADMIN)).fetchone()[0]:
                raise CannotStart("An admin, or another dbtool, is using the database %s. Stop it first." % ident.dbname)
            conn.autocommit = False
            return _migrate(cfg, conn, ident, params, args.apply, t0)
        finally:
            conn.close()


def _migrate(cfg, conn, ident, params, apply, t0):
    from bgsadmin.db import content, migrate as runner
    from bgsadmin.store.jsonstore import JSONStore
    actor = getpass.getuser()
    cur = conn.cursor()
    say(*target_lines(cfg, ident, params))
    runner.check_fresh_or_ours(cur)
    runner.check_binding(cur, cfg.repo)
    before = runner.applied(cur)
    done = runner.apply(cur, cfg.repo, actor)
    say("schema      %s, now %s" % (before[-1][1] if before else "none", runner.applied(cur)[-1][1]),
        "applied     %s" % (", ".join(done) if done else "nothing new"))
    snapshot = JSONStore(cfg).export_snapshot()
    parsed, bad = parse_all(snapshot)
    if bad:
        conn.rollback()
        say(*("unreadable  %s" % b for b in bad))
        say("Nothing was written (rolled back): the files above must be valid JSON first.")
        return 1
    fresh = cur.execute("SELECT NOT EXISTS (SELECT 1 FROM bgs.products) AND NOT EXISTS "
                        "(SELECT 1 FROM bgs.documents)").fetchone()[0]
    refused = []
    if fresh:
        _, refused = content.load(cur, parsed, actor)
        for r in refused:
            say("refused     %s%s: %s (%s)" % (r["name"] or "the commit", " " + r["id"] if r["id"] else "",
                                               r["message"], r["constraint"] or r["sqlstate"]))
    state = content.read(cur)
    exports = state.exports
    differ = []
    say("content     %-17s %9s  %-12s  %-12s  %s" % ("file", "bytes", "file sha", "export sha", ""))
    for n in content_names():
        disk, mine = snapshot[n], exports.get(n)
        if mine == disk:
            how = "identical"
        elif mine is not None and mine == canonical(parsed[n]):
            how = "formatting only: the same data"
        else:
            how = "DIFFERENT"
            differ.append(n)
        say("            %-17s %9d  %s  %s  %s" % (n + ".json", len(disk), sha(disk)[:12],
                                                   sha(mine)[:12] if mine is not None else "-" * 12, how))
    room = []
    if not differ and not refused:
        pr = parsed["products"]
        same = sum(1 for pid, d in pr.items() if rev_of(state.products.get(pid)) == rev_of(d))
        say("revs        collection %s; %d of %d product revs the same" % (
            "the same" if rev_of(state.products) == rev_of(pr) else "DIFFERENT", same, len(pr)))
        if fresh:
            content.set_bases(cur, {n: (sha(snapshot[n]), sha(exports[n])) for n in content_names()})
            compared, room = clean_room(cfg, exports)
            say(*("clean room  %s" % p for p in room))
            if not room:
                say("clean room  the site built from the database's export: all %d generated files identical"
                    % compared)
    elif not fresh:
        for n in differ:
            say(*("differs     %s.json: %s" % (n, s) for s in sentences(n, state.data(n) if n in exports else None,
                                                                       parsed[n])))
    say(rows_line(cur))
    ok = not refused and not differ and not room
    secs = "time        %.1f s" % (time.monotonic() - t0)
    nothing = "Nothing to do: the database already holds this checkout's schema and content."
    if ok and apply:
        conn.commit()
        say(secs, "Committed." if done or fresh else nothing)
        say(switch(cfg, conn, params))
        return 0
    conn.rollback()
    say(secs)
    if ok:
        say("DRY RUN: nothing was written (rolled back). Run the same line with --apply." if done or fresh else nothing)
        return 0
    say("Nothing was written (rolled back): see the lines above.")
    return 1

# ---- verify -------------------------------------------------------------------------

# The triggers migration 001 makes; every one must be there and enabled.
TRIGGERS_001 = (
    "products_before", "products_guard_never_discount", "products_refs_on_write", "products_refs_on_change",
    "products_revision_on_write", "products_revision_on_change", "products_bump", "products_no_truncate",
    "documents_before", "documents_refs_on_write", "documents_refs_on_change", "documents_revision_on_write",
    "documents_revision_on_change", "documents_bump", "documents_no_truncate", "revisions_audited",
    "locked_values_held", "revisions_append_only", "audit_log_append_only", "revisions_no_truncate",
    "audit_log_no_truncate")
TRIGGERS = ("SELECT t.tgname, t.tgenabled FROM pg_trigger AS t JOIN pg_class AS c ON c.oid = t.tgrelid "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace WHERE n.nspname = 'bgs' AND NOT t.tgisinternal")
NOT_VALID = ("SELECT c.conrelid::regclass::text || ' ' || c.conname FROM pg_constraint AS c "
             "JOIN pg_namespace AS n ON n.oid = c.connamespace WHERE n.nspname = 'bgs' AND NOT c.convalidated "
             "ORDER BY 1")

# What the admin's own role may change: everything else it may only read.
APP_ROLE = "bgs_corner_app"
APP_WRITES = {"products": {"INSERT", "UPDATE", "DELETE"}, "documents": {"INSERT", "UPDATE"},
              "content_files": {"INSERT", "UPDATE"}, "audit_log": {"INSERT"}}
APP_COLUMNS = {"products": {"pos", "body"}, "documents": {"body"},
               "content_files": {"name", "file_sha", "export_sha", "updated_at"}}
APP_CALLS = ("bgs.lock_content_state()", "bgs.prune_revisions(interval, integer)")
RIGHTS = ("SELECT c.relname, has_table_privilege(%(r)s, c.oid, 'SELECT'), "
          "has_any_column_privilege(%(r)s, c.oid, 'INSERT'), has_any_column_privilege(%(r)s, c.oid, 'UPDATE'), "
          "has_table_privilege(%(r)s, c.oid, 'DELETE'), has_table_privilege(%(r)s, c.oid, 'TRUNCATE'), "
          "pg_get_userbyid(c.relowner) = %(r)s "
          "FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace "
          "WHERE n.nspname = 'bgs' AND c.relkind IN ('r', 'p') ORDER BY c.relname")
COLUMNS = ("SELECT a.attname FROM pg_attribute AS a WHERE a.attrelid = %(t)s::regclass AND a.attnum > 0 "
           "AND NOT a.attisdropped AND has_column_privilege(%(r)s, a.attrelid, a.attnum, 'UPDATE')")
PROVIDERS = {"c": "libc", "i": "icu", "b": "builtin"}


def app_rights(cur, role=APP_ROLE):
    """What differs between the rights the admin's role has and the ones it
    should have."""
    out = []
    for name, reads, ins, upd, dele, trunc, owns in cur.execute(RIGHTS, {"r": role}).fetchall():
        may = APP_WRITES.get(name, set())
        have = {p for p, v in (("INSERT", ins), ("UPDATE", upd), ("DELETE", dele), ("TRUNCATE", trunc)) if v}
        if not reads:
            out.append("%s cannot read bgs.%s." % (role, name))
        if owns:
            out.append("%s owns bgs.%s." % (role, name))
        out += ["%s may %s bgs.%s, which it must not." % (role, p, name) for p in sorted(have - may)]
        out += ["%s may not %s bgs.%s, which the admin needs." % (role, p, name) for p in sorted(may - have)]
        if "UPDATE" in have and name in APP_COLUMNS:
            cols = {r[0] for r in cur.execute(COLUMNS, {"t": "bgs." + name, "r": role}).fetchall()}
            if cols - APP_COLUMNS[name]:
                out.append("%s may change %s in bgs.%s, which it must not." % (
                    role, ", ".join(sorted(cols - APP_COLUMNS[name])), name))
    for fn in APP_CALLS:
        if not cur.execute("SELECT has_function_privilege(%s, %s, 'EXECUTE')", (role, fn)).fetchone()[0]:
            out.append("%s may not call %s, which the admin needs." % (role, fn))
    return out


def file_state(disk, mine, base):
    """How a content file stands against the database's export and the base
    (the pair of shas from when the two last agreed)."""
    f = sha(disk) if disk is not None else None
    e = sha(mine) if mine is not None else None
    if e is None:
        return "no row in the database"
    if f is None:
        return "the file is missing"
    if f == e:
        return "in sync"
    if base and (f, e) == tuple(base):
        return "in sync (the file is formatted differently)"
    if base and f == base[0]:
        return "changed in the database"
    if base and e == base[1]:
        return "changed in the file"
    return "changed in both"


def own_dsn(cfg, args):
    """--dsn, else the DSN this checkout's admin starts on."""
    if args.dsn:
        return args.dsn
    try:
        local = config.read_store_choice(cfg.repo)
    except ValueError as e:
        raise CannotStart(str(e))
    if not local or not local.get("dsn"):
        raise CannotStart("Give --dsn: this checkout has no database of its own yet (dbtool migrate --apply gives "
                          "it one).")
    return local["dsn"]


def verify(cfg, args):
    import psycopg
    from bgsadmin.db import connect, content, migrate as runner
    dsn = own_dsn(cfg, args)
    params = connect.check_dsn(dsn)
    conn = connect.open_checked(dsn, params, app="bgs-dbtool", read_only=True)
    try:
        ident = connect.check_identity(conn, params)
        cur = conn.cursor()
        say(*target_lines(cfg, ident, params))
        if not runner.installed(cur):
            raise CannotStart("The database has no admin tables yet: run dbtool migrate first.")
        try:
            cur.execute("SELECT pg_advisory_xact_lock_shared(%s, %s)", (connect.LOCK_CLASS, connect.SAVE))
        except psycopg.errors.LockNotAvailable:
            raise CannotStart("A save held the database for more than 5 s. Run verify again in a moment.", 1)
        problems = []
        try:
            todo = runner.pending(cur)
        except CannotStart as e:
            problems.append(e.message)
            todo = []
        if todo:
            problems.append("The database still needs %s: run dbtool migrate --apply." % ", ".join(m.name for m in todo))
        say("schema      %s" % ", ".join(n for _, n, _ in runner.applied(cur)))
        bound = runner.bound_to(cur)
        say("bound to    %s" % bound)
        if bound != str(cfg.repo):
            problems.append("The database belongs to %s, not this checkout (%s)." % (bound, cfg.repo))
        trig = dict(cur.execute(TRIGGERS).fetchall())
        off = sorted(t for t, on in trig.items() if on != "O")
        notvalid = [r[0] for r in cur.execute(NOT_VALID).fetchall()]
        problems += ["The trigger %s is missing." % t for t in TRIGGERS_001 if t not in trig]
        problems += ["The trigger %s is switched off." % t for t in off]
        problems += ["The check %s is not validated." % c for c in notvalid]
        say("checks      %d triggers, %s; %s" % (len(trig), "%d switched off" % len(off) if off else "all enabled",
                                                 "%d checks not validated" % len(notvalid) if notvalid
                                                 else "every check validated"))
        if connect.app_role_exists(conn, APP_ROLE):
            wrong = app_rights(cur)
            problems += wrong
            say("admin role  %s: %s" % (APP_ROLE, "%d rights differ" % len(wrong) if wrong else
                                        "reads everything; writes content, the file bases and the audit trail"))
        else:
            say("admin role  %s does not exist: the admin runs as the database's owner" % APP_ROLE)
        state = content.read(cur)
        say("content     %-17s %-12s  %-12s  %-12s  %s" % ("file", "file sha", "export sha", "base file", "state"))
        for n in content_names():
            p = cfg.content_file(n)
            disk = p.read_bytes() if p.exists() else None
            mine, base = state.exports.get(n), state.bases.get(n)
            how = file_state(disk, mine, base)
            if not how.startswith("in sync"):
                problems.append("%s.json: %s." % (n, how))
            say("            %-17s %-12s  %-12s  %-12s  %s" % (
                n + ".json", sha(disk)[:12] if disk is not None else "-", sha(mine)[:12] if mine is not None else "-",
                base[0][:12] if base else "-", how))
        say(rows_line(cur))
        newest = cur.execute("SELECT id, at, actor, reason FROM bgs.revisions ORDER BY id DESC LIMIT 1").fetchone()
        if newest:
            say("newest      revision %d, %s, by %s: %s" % (newest[0], str(newest[1])[:19], newest[2], newest[3]))
        coll, prov = cur.execute("SELECT datcollate, datlocprovider FROM pg_database "
                                 "WHERE datname = current_database()").fetchone()
        say("locale      collation %s, provider %s" % (coll, PROVIDERS.get(prov, prov)))
        if problems:
            say("%d difference%s:" % (len(problems), "" if len(problems) == 1 else "s"), *("  " + p for p in problems))
            return 1
        say("OK: the database agrees with itself and with the files.")
        return 0
    finally:
        with contextlib.suppress(Exception):
            conn.rollback()
        conn.close()


# ---- use ------------------------------------------------------------------------------

def use(cfg, args):
    """Write admin/local/store.json. For postgres, the database is checked
    first: this checkout's, up to date, and answering."""
    from bgsadmin.db import connect, migrate as runner
    try:
        dsn = args.dsn or (config.read_store_choice(cfg.repo) or {}).get("dsn")
    except ValueError as e:
        raise CannotStart(str(e))
    if args.store == "json":
        config.write_store_choice(cfg.repo, "json", dsn)
        say("switched    this checkout's admin starts on the JSON files in flow/content from its next start",
            "Files saved there meanwhile show as changed outside the admin once it starts on the database again.")
        return 0
    if not dsn:
        raise CannotStart("Give --dsn: this checkout has no database yet (dbtool migrate --apply gives it one).")
    params = connect.check_dsn(dsn)
    conn = connect.open_checked(dsn, params, autocommit=True, app="bgs-dbtool", read_only=True)
    try:
        connect.check_identity(conn, params)
        runner.check_current(conn.cursor(), cfg.repo)
    finally:
        conn.close()
    config.write_store_choice(cfg.repo, "postgres", dsn)
    say("switched    this checkout's admin starts on the database %s as %s from its next start"
        % (params["dbname"], params["user"]))
    return 0


COMMANDS = {"migrate": migrate, "verify": verify, "use": use}

if __name__ == "__main__":
    sys.exit(main())
