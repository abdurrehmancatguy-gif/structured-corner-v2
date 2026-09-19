"""The PostgreSQL content store: the database holds the content, and every
save writes flow/content/*.json from it before the build, so build.py, git,
History and the Publish screen read the same files as before.

A save, in order:
1. what to write: each staged document in canonical form; the rows that
   change; the files that change (with any the database holds newer, and any
   file that is missing);
2. the database first, while nothing is on disk: one transaction that says
   who and why, writes the rows, the file bases and its audit row, makes
   every check at once (SET CONSTRAINTS ALL IMMEDIATE) and reads the export
   back. A refusal here is a ROLLBACK and an answer; no file was touched;
3. the journal, as the JSON store keeps it (store/files.py), naming the
   transaction; 4. the files; 5. make_derivatives and the tools when media
   changed, then build.py;
6. a failed build puts every file back and rolls the transaction back;
7. the manifest says committing, then COMMIT; 8. the before-images History
   lists, the audit line, and the journal goes.
A crash before COMMIT is undone by recover(), which puts the files back. For
a crash during COMMIT, recover() asks the database whether the save's audit
row is there, and finishes the save or undoes it.

Files changed outside the admin (a hand edit, git) are refused for now: the
database has not taken them, so external_changes() lists them and a save that
would write one answers 409 until the file is put back. A file the database
holds newer (changed in psql) or a missing one is written by the next save,
or by Rebuild now.

Three connections: one holds the session lock that makes this the only admin
on the database, one writes (under the save lock), one reads (one statement
per read, so each read is one snapshot).
"""
import contextlib
import copy
import fcntl
import getpass
import os
import shutil
import sys
import threading
import time
import traceback
import uuid

import psycopg

from .. import schema, tools
from ..db import connect, content, errors as dberrors, migrate
from ..errors import ApiError
from ..jsonutil import canonical, strict_loads
from . import files
from .base import CannotStart, ContentStore, Failed, actor_now, Txn as _Txn, content_names, rev_of, sha

OUTSIDE = ("file", "both")        # changed outside the admin: refused until the file is put back
STALE = ("database", "missing")   # the file is behind the database: written by the next save


def _read(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


class PGStore(ContentStore):
    def __init__(self, cfg, dsn=None):
        self.NAMES = content_names()
        self.cfg = cfg
        self.dsn = dsn or cfg.dsn
        self.params = connect.check_dsn(self.dsn)       # CannotStart before any connection
        self.actor = getpass.getuser()
        self.ident = None
        self.kept = []                  # journals recover() finished: the database had committed them
        self._gate = threading.Lock()   # guards _busy
        self._busy = None               # the reason of the save in progress
        self._lock = threading.Lock()   # held by a save from start to end, and by a read's file check
        self._rlock = threading.Lock()  # the reader connection
        self._lockfile = None
        self._conns = {"lock": None, "writer": None, "reader": None}
        self._state = None              # content.State the reads serve
        self._fstat = {}                # name -> (mtime_ns, size, sha) of its file
        self._outside = {}              # name -> how its file stands, when not in sync
        self._writing = set()           # the names the save in progress writes
        self._unsettled = None          # (journal folder, manifest) whose COMMIT outcome is not known

    # ---- lifecycle -----------------------------------------------------------------

    def describe(self):
        if self.ident is None:
            return "PostgreSQL %s" % self.params["dbname"]
        return "PostgreSQL %s as %s (%s)" % (self.ident.dbname, self.ident.user, self.ident.version.split()[0])

    def warnings(self):
        if self.ident is not None and self.ident.owner:
            return ["running as %s, the database's owner: create bgs_corner_app (admin/README.md, Database) and run "
                    "dbtool migrate --apply again, so the locked settings are a permission as well as a trigger"
                    % self.ident.user]
        return []

    def open(self):
        """Take this checkout's lock and the database's, check the database
        is this checkout's and up to date, settle the saves a crash cut
        short, sweep stray temporary files and prime the reads. CannotStart
        (2 refused, 3 not answering) when it cannot."""
        cfg = self.cfg
        cfg.backups.mkdir(parents=True, exist_ok=True)
        self._lockfile = open(str(cfg.backups / ".admin.lock"), "a+")
        try:
            fcntl.flock(self._lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lockfile.close()
            self._lockfile = None
            raise CannotStart("Another admin is already running for %s. Stop it first." % cfg.repo)
        try:
            lock = connect.open_checked(self.dsn, self.params, autocommit=True)
            self._conns["lock"] = lock
            self.ident = connect.check_identity(lock, self.params)
            if not lock.execute("SELECT pg_try_advisory_lock(%s, %s)", (connect.LOCK_CLASS, connect.ADMIN)).fetchone()[0]:
                raise CannotStart("Another admin is already using the database %s. Stop it first." % self.ident.dbname)
            cur = lock.cursor()
            migrate.check_current(cur, cfg.repo)
            have = {r[0] for r in cur.execute("SELECT key FROM bgs.documents").fetchall()}
            missing = [n for n in schema.document_names() if n not in have]
            if missing:
                raise CannotStart("The database has no %s: a new document needs a migration before the admin can "
                                  "edit it." % ", ".join(missing))
            recovered = self.recover()
            for p in cfg.content.glob(".*.tmp"):
                with contextlib.suppress(FileNotFoundError):
                    p.unlink()
            with self._lock:
                self._refresh()
                self._check_files()
            return recovered
        except psycopg.Error as e:
            self.close()
            raise connect.not_answering(self.params, e) if dberrors.is_lost(e) else CannotStart(
                "The database refused the admin at start: %s" % str(e).strip().splitlines()[0])
        except BaseException:
            self.close()
            raise

    def close(self):
        """Let go of the connections (and so the database's lock) and this
        checkout's lock. Closing twice does nothing."""
        for kind in ("reader", "writer", "lock"):
            c, self._conns[kind] = self._conns.get(kind), None
            if c is not None:
                with contextlib.suppress(Exception):
                    c.close()
        f, self._lockfile = self._lockfile, None
        if f is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(f, fcntl.LOCK_UN)
            f.close()

    def _conn(self, kind):
        """The reader or writer connection, opened again if it broke."""
        c = self._conns.get(kind)
        if c is None or c.closed or c.broken:
            if c is not None:
                with contextlib.suppress(Exception):
                    c.close()
            c = self._conns[kind] = connect.connect(self.dsn, autocommit=(kind != "writer"))
        return c

    def _db_error(self, e, deleted=(), dangling=()):
        """The ApiError for a psycopg error; a store bug is logged."""
        err = dberrors.answer(e, deleted, dangling)
        if err.status == 500:
            sys.stderr.write("bgs-admin: the database refused a save: %s\n" % str(e).strip())
            traceback.print_exc()
        return err

    # ---- saves a crash cut short ---------------------------------------------------------

    def recover(self):
        """Settle every save a crash cut short; returns their journals.
        prepared or applied: COMMIT was never sent (the server rolls back a
        transaction whose client died), so the files are put back.
        committing: the database says whether it kept the save; if it did,
        the files stay and History's before-images are written from the
        journal; if not, the files are put back. A database that cannot say
        stops the start (either guess could lose a save)."""
        done = []
        for d, man in files.journals(self.cfg):
            if man is None:
                continue
            state = man.get("state")
            if state == "committing":
                self._finish(d, man, self._outcome(man))
                done.append(d.name)
            elif state in ("prepared", "applied"):
                files.restore(man["files"], d)
                files.audit(self.cfg, {"action": "recover", "reason": man.get("reason"), "txn": d.name, "ok": True})
                done.append(d.name)
            shutil.rmtree(str(d), ignore_errors=True)
        return done

    def _outcome(self, man):
        """Whether the database committed a journal's save: its ok audit_log
        row is there, or its transaction's status is committed. The row is
        read with the statement's snapshot and the status at call time, so a
        COMMIT that lands between the two reads shows as (no row, committed):
        that save was kept, with its row. Only aborted (or no status) means
        it was not. While its transaction is still in progress (the server
        has not seen the client go yet), wait up to 5 s. CannotStart (3) when
        the database does not answer, or cannot say."""
        txn, xid = man.get("txn"), man.get("xid")
        if not txn:
            return False
        try:
            with connect.connect(self.dsn, autocommit=True) as c:
                for _ in range(50):
                    kept, status = c.execute(
                        "SELECT EXISTS (SELECT 1 FROM bgs.audit_log WHERE txn = %s AND ok), pg_xact_status(%s::xid8)",
                        (txn, xid)).fetchone()
                    if kept or status == "committed":
                        return True
                    if status != "in progress":
                        return False
                    time.sleep(0.1)
        except psycopg.Error as e:
            raise connect.not_answering(self.params, e) if dberrors.is_lost(e) else CannotStart(str(e).strip())
        raise CannotStart("The database has not yet settled the save that was committing when the admin stopped "
                          "(%s). Start the admin again in a moment." % txn, 3)

    def _finish(self, d, man, kept):
        """Finish a committing journal's save the database kept (the files
        stay; the before-images are written from the journal's copies under
        the save's stamp), or put its files back."""
        if kept:
            st = man.get("stamp") or files.stamp()
            by_path = {str(self.cfg.content_file(n)): n for n in self.NAMES}
            for f in man["files"]:
                name = by_path.get(f["path"])
                if name and f.get("snap") and name in man.get("written", [name]):
                    files.write_backup(self.cfg, name, st, (d / f["snap"]).read_bytes())
            self.kept.append(d.name)
            files.audit(self.cfg, {"action": "recover-forward", "reason": man.get("reason"), "txn": d.name, "ok": True})
        else:
            files.restore(man["files"], d)
            files.audit(self.cfg, {"action": "recover", "reason": man.get("reason"), "txn": d.name, "ok": True})

    def _settle(self):
        """A save whose COMMIT outcome was not known when the database went
        away: settle it before any other save, or answer 503 while the
        database still cannot say."""
        if self._unsettled is None:
            return
        d, man = self._unsettled
        try:
            kept = self._outcome(man)
        except CannotStart:
            raise dberrors.unavailable()
        self._finish(d, man, kept)
        shutil.rmtree(str(d), ignore_errors=True)
        self._unsettled = None
        self._state = None

    # ---- reading ---------------------------------------------------------------------------

    def _read_state(self):
        with self._rlock:
            return content.read(self._conn("reader").cursor())

    def _refresh(self):
        """The content, read again when the database's version moved (a save,
        or a change made in psql)."""
        st = self._state
        if st is not None:
            with self._rlock:
                v = self._conn("reader").execute("SELECT version FROM bgs.content_state").fetchone()[0]
            if v == st.version:
                return st
        st = self._state = self._read_state()
        return st

    def _current(self):
        """The content reads serve: fresh, with the files checked, when no save
        is running. While one is, the content from before it: the check never
        runs during a save, which writes files the database has not
        committed yet."""
        try:
            if self._lock.acquire(blocking=False):
                try:
                    st = self._refresh()
                    self._check_files()
                    return st
                finally:
                    self._lock.release()
            st = self._state
            if st is None:
                st = self._state = self._read_state()
            return st
        except psycopg.Error as e:
            raise self._db_error(e)

    def doc(self, name):
        if name == "products":
            return self.products()
        st = self._current()
        if name not in st.docs:
            raise ApiError(404, "not_found", "There is no document %s." % name)
        return copy.deepcopy(st.docs[name]), sha(st.exports[name])[:16]

    def products(self):
        st = self._current()
        return copy.deepcopy(st.products), sha(st.exports["products"])[:16]

    def product(self, pid):
        st = self._current()
        if not isinstance(pid, str) or pid not in st.products:
            raise ApiError(404, "not_found", "There is no product with the id %s." % pid)
        d = copy.deepcopy(st.products[pid])
        return d, rev_of(d)

    def export_snapshot(self):
        """Every content file as the database writes it, from one statement:
        one snapshot, in content_names() order, drafts included."""
        try:
            return dict(self._read_state().exports)
        except psycopg.Error as e:
            raise self._db_error(e)

    def external_changes(self):
        """The files not in sync with the database, in content_names() order:
        changed outside the admin, missing, or behind the database. While a
        save runs, the names it is writing are left out."""
        self._current()
        writing = self._writing if self._busy else set()
        return [n for n in self.NAMES if n in self._outside and n not in writing]

    def acknowledge(self):
        """The owner has seen the notice ("Got it"). A file changed outside
        the admin stays listed until it is put back: the database has not
        taken it, and a save over it would lose it."""

    def busy(self):
        return self._busy

    # ---- the files against the database -------------------------------------------------------

    def _file_sha(self, name):
        """The sha of a content file, hashed again only when its size or
        mtime moved; None when it is missing."""
        p = self.cfg.content_file(name)
        try:
            s = os.stat(str(p))
        except FileNotFoundError:
            self._fstat.pop(name, None)
            return None
        c = self._fstat.get(name)
        if c is not None and c[:2] == (s.st_mtime_ns, s.st_size):
            return c[2]
        h = sha(p.read_bytes())
        self._fstat[name] = (s.st_mtime_ns, s.st_size, h)
        return h

    def _same_data(self, name, st):
        try:
            return canonical(strict_loads(self.cfg.content_file(name).read_bytes())) == st.exports[name]
        except (OSError, ApiError):
            return False

    def _check_files(self):
        """Under the save lock: how each file stands against the database's
        export and its base, the shas of the file and of the export when the
        two last agreed. In sync: the pair is the base, or the file is the
        export, or it holds the same data in other formatting (then the pair
        becomes the base). Otherwise "missing", "database" (only the export
        moved: the next save writes the file), or "file" and "both" (the file
        was changed outside the admin)."""
        st = self._state
        out, new = {}, {}
        for n in self.NAMES:
            f, e, b = self._file_sha(n), sha(st.exports[n]), st.bases.get(n)
            if f is None:
                out[n] = "missing"
            elif b is not None and (f, e) == tuple(b):
                continue
            elif f == e:
                new[n] = (f, e)
            elif b is not None and f == b[0]:
                out[n] = "database"
            elif self._same_data(n, st):
                new[n] = (f, e)
            else:
                out[n] = "file" if b is not None and e == b[1] else "both"
        if new:
            w = self._conn("writer")
            with w.transaction():
                content.set_bases(w.cursor(), new)
            st.bases.update(new)
        self._outside = out

    # ---- writing ----------------------------------------------------------------------------

    @contextlib.contextmanager
    def transaction(self, reason):
        """One save at a time: 423 busy at once while another save runs. A
        read checking the files holds the save lock for a moment, so a save
        waits for that rather than answering busy."""
        with self._gate:
            if self._busy is not None:
                raise ApiError(423, "busy", "Another change is still saving (%s). Try again in a moment." % self._busy,
                               {"operation": self._busy})
            self._busy = reason
        try:
            self._lock.acquire()
            try:
                try:
                    self._settle()
                    self._refresh()
                    self._check_files()
                except psycopg.Error as e:
                    raise self._db_error(e)
                txn = PGTxn(self, reason)
                yield txn
                txn.commit()
            finally:
                self._writing = set()
                self._lock.release()
        finally:
            with self._gate:
                self._busy = None


# ---- the transaction -------------------------------------------------------------------------

class PGTxn(_Txn):
    def __init__(self, store, reason):
        super().__init__(store, reason)
        self.state = store._state          # every load() copies this: the content from before the save

    def load(self, name):
        if name not in self.docs:
            self.docs[name] = copy.deepcopy(self.state.data(name))
        return self.docs[name]

    def commit(self):
        store, cfg, st = self.store, self.cfg, self.state
        new = {n: canonical(self.docs[n]) for n in store.NAMES if n in self.dirty}
        db_writes = [n for n in store.NAMES if n in new and new[n] != st.exports[n]]
        disk = {n: _read(cfg.content_file(n)) for n in store.NAMES}
        target = dict(new)
        for n, how in store._outside.items():
            if how in STALE:                   # the file is behind the database: this save writes it too
                target.setdefault(n, st.exports[n])
        file_writes = [n for n in store.NAMES if n in target and target[n] != disk[n]]
        if not db_writes and not any(n in new for n in file_writes) and not self.media and not self.force:
            self.result = {"changed": [], "build": None}
            return
        blocked = [n for n in store.NAMES if store._outside.get(n) in OUTSIDE and (n in db_writes or n in file_writes)]
        if blocked:
            paths = ["flow/content/%s.json" % n for n in blocked]
            one = len(paths) == 1
            raise ApiError(409, "changed_outside", "%s %s changed outside the admin, and the database has not taken %s. "
                           "Put %s back (git checkout -- %s), then save again." % (
                               " and ".join(paths), "was" if one else "were", "it" if one else "them",
                               "the file" if one else "the files", " ".join(paths)), {"names": blocked})
        store._writing = set(file_writes) | set(db_writes)
        stamp = files.stamp()
        txid = uuid.uuid4() if db_writes else None
        w = xid = None
        if db_writes:
            w, xid = self._write_db(txid, new, db_writes)
        journal = None
        try:
            paths = files.journal_paths(cfg, [cfg.content_file(n) for n in file_writes], self.extra, self.media)
            journal = files.Journal(cfg, paths, {"reason": self.reason, "actor": actor_now(store.actor), "store": "postgres",
                                                 "txn": str(txid) if txid else None, "xid": xid, "stamp": stamp,
                                                 "written": sorted(file_writes)})
            before = tools.scan(cfg.flow)
            for n in file_writes:
                files.atomic_write(cfg.content_file(n), target[n])
            self.place_media()
            journal.set_state("applied")
            build = self.build(paths, before)
        except Failed as f:
            journal.restore()
            self._rollback(w)
            self._audit_failed(f.problems, file_writes)
            files.audit(cfg, {"action": self.reason, "ok": False, "problems": f.problems,
                              "changed": sorted(file_writes), "actor": actor_now(store.actor)})
            journal.remove()
            store._state = None
            raise ApiError(422, "build_failed", "Your change was not applied: the site would not build with it.",
                           {"problems": f.problems, "restored": True})
        except BaseException:
            if journal is not None:
                journal.restore()
                journal.remove()
            self._rollback(w)
            store._state = None
            raise
        if w is not None:
            self._commit(w, journal)
        for n in file_writes:
            if disk[n] is not None:
                files.write_backup(cfg, n, stamp, disk[n])
        journal.set_state("committed")
        changed = sorted(set(file_writes) | set(db_writes))
        entry = {"action": self.reason, "ok": True, "changed": changed, "build_ms": build["ms"], "actor": actor_now(store.actor)}
        if self.confirmed:
            entry["confirmed"] = list(self.confirmed)
        files.audit(cfg, entry)
        journal.remove()
        store._state = None
        self.result = {"changed": changed, "build": {"ok": True, "ms": build["ms"], "problems": []}}

    def _write_db(self, txid, new, names):
        """The database side of the save, before any file is written. Returns
        (connection, xid) with the transaction still open; or rolls it back
        and raises the answer."""
        store, st = self.store, self.state
        products = self.docs.get("products") if "products" in names else None
        deleted = [pid for pid in st.products if products is not None and pid not in products]
        w = None
        try:
            w = store._conn("writer")
            cur = w.cursor()
            if not cur.execute("SELECT pg_try_advisory_xact_lock(%s, %s)",
                               (connect.LOCK_CLASS, connect.SAVE)).fetchone()[0]:
                raise ApiError(423, "busy", dberrors.BUSY[0], dict(dberrors.BUSY[1]))
            if content.lock_version(cur) != st.version:
                raise ApiError(412, "stale_rev", "This changed since you opened it: another program changed the "
                                                 "database. Reload and try again.")
            content.begin(cur, txid, actor_now(store.actor), self.reason, self.confirmed)
            content.write_changes(cur, st, products, {n: self.docs[n] for n in names if n != "products"})
            content.set_bases(cur, {n: (sha(new[n]), sha(new[n])) for n in names})
            content.audit(cur, txid, actor_now(store.actor), self.reason, names)
            cur.execute("SAVEPOINT bgs_checks")
            try:
                cur.execute("SET CONSTRAINTS ALL IMMEDIATE")
            except psycopg.Error as e:
                if e.sqlstate != "23503":
                    raise
                cur.execute("ROLLBACK TO SAVEPOINT bgs_checks")
                raise store._db_error(e, deleted, content.dangling(cur))
            back = content.read(cur).exports
            odd = [n for n in names if back.get(n) != new[n]]
            if odd:
                sys.stderr.write("bgs-admin: the database gave back other bytes for %s than the save wrote\n"
                                 % ", ".join(odd))
                raise ApiError(500, "internal", "The database gave back something other than what was saved, so "
                                                "nothing was kept. The server's terminal has the details.")
            return w, cur.execute("SELECT pg_current_xact_id()::text").fetchone()[0]
        except ApiError:
            self._rollback(w)
            raise
        except UnicodeEncodeError:
            self._rollback(w)
            raise ApiError(422, "validation", "Some fields need attention.",
                           [{"path": "", "code": "control", "message": "Text may not hold half of a character pair."}])
        except psycopg.Error as e:
            self._rollback(w)
            raise store._db_error(e, deleted)
        except BaseException:
            self._rollback(w)
            raise

    def _commit(self, w, journal):
        """COMMIT, with the manifest saying so first. A COMMIT the server
        refused kept nothing: the files go back. A connection that broke
        during COMMIT leaves the outcome to the database, asked on a fresh
        connection; while it cannot say, the journal stays and every save
        answers 503 until it can (store._settle)."""
        store = self.store
        journal.set_state("committing")
        try:
            w.commit()
            return
        except psycopg.Error as e:
            store._state = None
            if not dberrors.is_lost(e):
                journal.restore()
                journal.remove()
                self._rollback(w)
                raise store._db_error(e)
        try:
            kept = store._outcome(journal.man)
        except CannotStart:
            store._unsettled = (journal.dir, journal.man)
            raise dberrors.unavailable()
        if not kept:
            journal.restore()
            journal.remove()
            raise dberrors.unavailable()

    @staticmethod
    def _rollback(w):
        if w is not None and not w.closed:
            with contextlib.suppress(Exception):
                w.rollback()

    def _audit_failed(self, problems, names):
        """The refused save's own audit row (ok false), in a short transaction
        of its own. Best effort: the answer does not depend on it."""
        store = self.store
        with contextlib.suppress(Exception):
            w = store._conn("writer")
            with w.transaction():
                content.audit(w.cursor(), uuid.uuid4(), actor_now(store.actor), self.reason, names, ok=False, problems=problems)
