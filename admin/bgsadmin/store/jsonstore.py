"""The JSON content store: flow/content/*.json, written so a save can never
leave the site half-changed.

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
back by recover().
"""
import contextlib
import copy
import datetime
import fcntl
import getpass
import hashlib
import json
import os
import pathlib
import secrets
import shutil
import tempfile
import threading

from .. import schema, tools
from ..errors import ApiError
from ..jsonutil import canonical
from .base import ContentStore


def sha(b):
    return hashlib.sha256(b).hexdigest()


def rev_of(obj):
    return sha(canonical(obj))[:16]


def stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def atomic_write(path, data):
    """Write to a temporary file beside the target, flush it to the disk
    (F_FULLFSYNC: on macOS plain fsync leaves it in the drive's cache), then
    rename over the target, so a reader sees the old file or the new one."""
    d = os.path.dirname(str(path))
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(str(path)) + ".", suffix=".tmp", dir=d)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
            with contextlib.suppress(AttributeError, OSError):
                fcntl.fcntl(f.fileno(), fcntl.F_FULLFSYNC)
        os.chmod(tmp, 0o644)
        os.replace(tmp, str(path))
        dfd = os.open(d, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(tmp)
        raise


class _Failed(Exception):
    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


class JSONStore(ContentStore):
    def __init__(self, cfg):
        self.NAMES = ("products",) + tuple(schema.document_names())
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
            raise SystemExit("Another admin is already running for %s. Stop it first." % self.cfg.repo)
        recovered = self.recover()
        for p in self.cfg.content.glob(".*.tmp"):
            with contextlib.suppress(FileNotFoundError):
                p.unlink()
        for n in self.NAMES:
            self._read(n)
        return recovered

    def recover(self):
        done = []
        root = self.cfg.backups / "txn"
        for m in sorted(root.glob("*/manifest.json")):
            try:
                man = json.loads(m.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if man.get("state") in ("prepared", "applied"):
                _restore(man["files"], m.parent)
                _audit(self.cfg, {"action": "recover", "reason": man.get("reason"), "txn": m.parent.name, "ok": True})
                done.append(m.parent.name)
            shutil.rmtree(m.parent, ignore_errors=True)
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


class Txn:
    def __init__(self, store, reason):
        self.store = store
        self.cfg = store.cfg
        self.reason = reason
        self.docs = {}
        self.dirty = set()
        self.media = False
        self.force = False        # rebuild even with nothing to write ("Rebuild now")
        self.extra = []           # more files to snapshot (media stages add theirs)
        self.files = []           # (destination, finished file) placed once the snapshot is taken
        self.removed = []         # published files taken away (to the trash) after the snapshot
        self.tools = []           # tools that run after make_derivatives, such as the favicon
        self.result = None

    def load(self, name):
        if name not in self.docs:
            data, _ = self.store._read(name)
            self.docs[name] = copy.deepcopy(data)
        return self.docs[name]

    def put(self, name, data):
        self.docs[name] = data
        self.dirty.add(name)

    def snapshot(self, path):
        path = pathlib.Path(path)
        if path not in self.extra:
            self.extra.append(path)

    def add_file(self, path, src):
        """Media made by this transaction. src is a finished file outside
        flow/assets; it is put at path only after the snapshot is taken, so a
        failed build removes it again, or puts back the file it replaced. The
        sized copies make_derivatives will write for it are snapshotted too,
        so a failed build leaves none of them behind."""
        from .. import media
        self.media = True
        self.snapshot(path)
        for c in media.sized_copies(self.cfg, path):
            self.snapshot(c)
        self.files.append((pathlib.Path(path), pathlib.Path(src)))

    def remove_file(self, path):
        """A published file taken away (its copy already sits in the trash).
        Snapshotted first, so a failed build puts it back."""
        self.media = True
        self.snapshot(path)
        self.removed.append(pathlib.Path(path))

    def run_tool(self, name):
        """Run one more tool from tools.TOOLS after make_derivatives, before the
        build. Its outputs must be snapshotted by the caller (with
        snapshot()) so a failed build puts them back."""
        if name not in self.tools:
            self.tools.append(name)

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
        tdir = cfg.backups / "txn" / ("%s-%s" % (stamp(), secrets.token_hex(3)))
        tdir.mkdir(parents=True)
        files = []
        paths = [cfg.content_file(n) for n in writes] + cfg.generated_files() + list(self.extra)
        if self.media:
            # make_derivatives sweeps sized copies whose original is gone; snapshot
            # them (and so allow their removal) or a save right after a file changed
            # outside the admin would fail on the sweep and not put the copy back.
            from .. import media
            have = set(paths)
            paths += [o for o in media.orphan_copies(cfg) if o not in have]
        for i, p in enumerate(paths):
            if p.exists():
                shutil.copy2(p, tdir / ("%d.bin" % i))
                files.append({"path": str(p), "snap": "%d.bin" % i})
            else:
                files.append({"path": str(p), "snap": None})
        man = {"state": "prepared", "reason": self.reason, "actor": self.store.actor, "files": files}
        _write_manifest(tdir, man)
        before = tools.scan(cfg.flow)
        build = None
        try:
            for name, (new, _) in writes.items():
                atomic_write(cfg.content_file(name), new)
            for dst, src in self.files:
                atomic_write(dst, src.read_bytes())
            for p in self.removed:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(p)
            man["state"] = "applied"
            _write_manifest(tdir, man)
            if self.media:
                for name in ["derivatives"] + self.tools:
                    d = tools.run(cfg, name)
                    if not d["ok"]:
                        raise _Failed(d["problems"])
            build = tools.run(cfg, "build")
            if not build["ok"]:
                raise _Failed(build["problems"])
            allowed = {os.path.relpath(str(p), str(cfg.flow)) for p in paths}
            odd = tools.unexpected(before, tools.scan(cfg.flow), allowed if not self.media else allowed | self._media_allowed())
            if odd:
                raise _Failed(["The build changed files it should not have: %s" % ", ".join(odd[:6])])
        except _Failed as f:
            _restore(files, tdir, cfg, before)
            _audit(cfg, {"action": self.reason, "ok": False, "problems": f.problems,
                         "changed": sorted(writes), "actor": self.store.actor})
            shutil.rmtree(tdir, ignore_errors=True)
            self.store._cache.clear()
            raise ApiError(422, "build_failed", "Your change was not applied: the site would not build with it.",
                           {"problems": f.problems, "restored": True})
        except BaseException:
            _restore(files, tdir, cfg, before)
            shutil.rmtree(tdir, ignore_errors=True)
            self.store._cache.clear()
            raise
        st = stamp()
        for name, (new, old) in writes.items():
            (cfg.backups / ("%s.%s.json" % (name, st))).write_bytes(old)
            self.store._known[name] = sha(new)
        man["state"] = "committed"
        _write_manifest(tdir, man)
        _audit(cfg, {"action": self.reason, "ok": True, "changed": sorted(writes),
                     "build_ms": build["ms"] if build else None, "actor": self.store.actor})
        shutil.rmtree(tdir, ignore_errors=True)
        self.result = {"changed": sorted(writes), "build": {"ok": True, "ms": build["ms"] if build else None, "problems": []}}

    def _media_allowed(self):
        """What a media transaction may change besides its snapshotted files:
        exactly the files it placed or removed, the sized copies
        make_derivatives writes or deletes for them, derivatives.json, and the
        favicon set when the emblem was replaced. Anything else changing (a
        stale copy of some other photo rewritten, say) still fails the save."""
        from .. import media
        cfg = self.cfg
        out = {"tools/derivatives.json"}
        for p in [d for d, _ in self.files] + self.removed:
            out.add(os.path.relpath(str(p), str(cfg.flow)))
            out.update(os.path.relpath(str(c), str(cfg.flow)) for c in media.sized_copies(cfg, p))
        if "favicon" in self.tools:
            out.update(media.FAVICON_OUTPUTS)
        return out


def _write_manifest(tdir, man):
    atomic_write(tdir / "manifest.json", json.dumps(man, indent=1).encode("utf-8"))


def _restore(files, tdir, cfg=None, before=None):
    """Put every snapshotted file back exactly; remove files that did not
    exist when the transaction began."""
    for f in files:
        p = f["path"]
        if f.get("snap"):
            data = (tdir / f["snap"]).read_bytes()
            try:
                cur = open(p, "rb").read()
            except FileNotFoundError:
                cur = None
            if cur != data:
                atomic_write(p, data)
        else:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(p)


def _audit(cfg, entry):
    entry = dict(entry, at=datetime.datetime.now().isoformat(timespec="seconds"))
    with contextlib.suppress(OSError):
        with open(cfg.backups / "audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
