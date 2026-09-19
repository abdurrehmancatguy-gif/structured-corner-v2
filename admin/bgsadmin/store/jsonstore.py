"""The JSON content store: flow/content/*.json are the content, written so a
save can never leave the site half-changed.

Every save is a transaction:
1. validated changes are staged in memory;
2. a journal is opened in .backups/txn/ with a snapshot of every content file
   it will write and of everything build.py writes (the pages, catalogue.js,
   flow.min.css, derivatives.json): build.py writes its output before its own
   checks run, so a failed build would otherwise leave a half-applied site;
3. the content files are replaced atomically;
4. build.py runs; any failure, or any file changed outside the expected
   outputs, puts every snapshot back byte for byte and removes new files;
5. on success the previous content is kept as a timestamped backup.
A journal still open at startup (the process was killed mid-save) is rolled
back by recover(). The journal, the writes and the build step are the ones
every store uses (files.py, base.Txn).
"""
import contextlib
import copy
import fcntl
import getpass
import json
import os
import shutil
import threading

from .. import tools
from ..errors import ApiError
from ..jsonutil import canonical
from . import files
from .base import ContentStore, Failed, actor_now, Txn as _Txn, content_names, rev_of, sha  # noqa: F401 (rev_of: kept importable from here)


class JSONStore(ContentStore):
    def __init__(self, cfg):
        self.NAMES = content_names()
        self.cfg = cfg
        self._lock = threading.Lock()
        self._busy = None
        self._cache = {}          # name -> (mtime_ns, size, data, bytes)
        self._known = {}          # name -> sha of the bytes the admin last read or wrote
        self._lockfile = None
        self.actor = getpass.getuser()

    # ---- lifecycle ---------------------------------------------------------

    def open(self):
        """Take the repository's admin lock, finish any interrupted save and
        sweep stray temporary files. Returns the journals it rolled back."""
        self.cfg.backups.mkdir(parents=True, exist_ok=True)
        self._lockfile = open(self.cfg.backups / ".admin.lock", "a+")
        try:
            fcntl.flock(self._lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self._lockfile.close()
            self._lockfile = None
            raise SystemExit("Another admin is already running for %s. Stop it first." % self.cfg.repo)
        recovered = self.recover()
        for p in self.cfg.content.glob(".*.tmp"):
            with contextlib.suppress(FileNotFoundError):
                p.unlink()
        for n in self.NAMES:
            self._read(n)
        return recovered

    def close(self):
        """Let go of the admin lock, so another admin (or open() again) can
        take it. Closing twice does nothing."""
        f, self._lockfile = self._lockfile, None
        if f is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(f, fcntl.LOCK_UN)
            f.close()

    def recover(self):
        found = files.journals(self.cfg)
        # A PostgreSQL save that was sending COMMIT: only the database knows
        # whether it kept it, and putting the files back could undo a save it
        # kept. Leave every journal as it is and say what to do.
        waiting = [d.name for d, man in found
                   if man and man.get("store") == "postgres" and man.get("state") == "committing"]
        if waiting:
            raise SystemExit(
                "A save to the PostgreSQL database was being committed when the admin stopped (%s). Only the "
                "database can say whether it kept it, so the JSON store leaves it alone. Start the admin on the "
                "PostgreSQL store once to settle it (admin/.venv/bin/python admin/server.py)." % ", ".join(waiting))
        done = []
        for d, man in found:
            if man is None:
                continue
            if man.get("state") in ("prepared", "applied"):
                files.restore(man["files"], d)
                files.audit(self.cfg, {"action": "recover", "reason": man.get("reason"), "txn": d.name, "ok": True})
                done.append(d.name)
            shutil.rmtree(d, ignore_errors=True)
        return done

    # ---- reading -----------------------------------------------------------

    def _read(self, name):
        p = self.cfg.content_file(name)
        st = os.stat(p)
        c = self._cache.get(name)
        if not c or c[0] != st.st_mtime_ns or c[1] != st.st_size:
            b = p.read_bytes()
            c = (st.st_mtime_ns, st.st_size, json.loads(b.decode("utf-8")), b)
            self._cache[name] = c
            self._known.setdefault(name, sha(b))
        return c[2], c[3]

    def doc(self, name):
        data, b = self._read(name)
        return copy.deepcopy(data), sha(b)[:16]

    def products(self):
        data, b = self._read("products")
        return copy.deepcopy(data), sha(b)[:16]

    def product(self, pid):
        data, _ = self._read("products")
        if not isinstance(pid, str) or pid not in data:
            raise ApiError(404, "not_found", "There is no product with the id %s." % pid)
        d = copy.deepcopy(data[pid])
        return d, rev_of(d)

    def export_snapshot(self):
        """Every content file's bytes as they are on disk, in NAMES order.
        Raw, not written again: a file that is not in canonical form shows
        as one. Needs no open(): it takes no lock and settles nothing."""
        return {n: self.cfg.content_file(n).read_bytes() for n in self.NAMES}

    def external_changes(self):
        out = []
        for n in self.NAMES:
            try:
                b = self.cfg.content_file(n).read_bytes()
            except FileNotFoundError:
                out.append(n)
                continue
            if n in self._known and sha(b) != self._known[n]:
                out.append(n)
        return out

    def acknowledge(self):
        """The owner reloaded after an outside edit: take the files as they are."""
        for n in self.NAMES:
            with contextlib.suppress(FileNotFoundError):
                self._known[n] = sha(self.cfg.content_file(n).read_bytes())

    def busy(self):
        return self._busy

    # ---- writing -----------------------------------------------------------

    @contextlib.contextmanager
    def transaction(self, reason):
        if not self._lock.acquire(blocking=False):
            raise ApiError(423, "busy", "Another change is still saving (%s). Try again in a moment." % (self._busy or "a save"),
                           {"operation": self._busy})
        self._busy = reason
        try:
            txn = Txn(self, reason)
            yield txn
            txn.commit()
        finally:
            self._busy = None
            self._lock.release()


class Txn(_Txn):
    def load(self, name):
        if name not in self.docs:
            data, _ = self.store._read(name)
            self.docs[name] = copy.deepcopy(data)
        return self.docs[name]

    def commit(self):
        cfg = self.cfg
        writes = {}
        for name in sorted(self.dirty):
            new = canonical(self.docs[name])
            old = cfg.content_file(name).read_bytes()
            if new != old:
                writes[name] = (new, old)
        if not writes and not self.media and not self.force:
            self.result = {"changed": [], "build": None}
            return
        paths = files.journal_paths(cfg, [cfg.content_file(n) for n in writes], self.extra, self.media)
        journal = files.Journal(cfg, paths, {"reason": self.reason, "actor": actor_now(self.store.actor)})
        before = tools.scan(cfg.flow)
        try:
            for name, (new, _) in writes.items():
                files.atomic_write(cfg.content_file(name), new)
            self.place_media()
            journal.set_state("applied")
            build = self.build(paths, before)
        except Failed as f:
            journal.restore()
            files.audit(cfg, {"action": self.reason, "ok": False, "problems": f.problems,
                              "changed": sorted(writes), "actor": actor_now(self.store.actor)})
            journal.remove()
            self.store._cache.clear()
            raise ApiError(422, "build_failed", "Your change was not applied: the site would not build with it.",
                           {"problems": f.problems, "restored": True})
        except BaseException:
            journal.restore()
            journal.remove()
            self.store._cache.clear()
            raise
        st = files.stamp()
        for name, (new, old) in writes.items():
            files.write_backup(cfg, name, st, old)
            self.store._known[name] = sha(new)
        journal.set_state("committed")
        entry = {"action": self.reason, "ok": True, "changed": sorted(writes), "build_ms": build["ms"],
                 "actor": actor_now(self.store.actor)}
        if self.confirmed:
            entry["confirmed"] = list(self.confirmed)
        files.audit(cfg, entry)
        journal.remove()
        self.result = {"changed": sorted(writes), "build": {"ok": True, "ms": build["ms"], "problems": []}}
