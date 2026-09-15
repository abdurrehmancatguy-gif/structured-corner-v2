"""The file side of a save, the same in every store.

Whatever holds the content, a save that writes goes through a journal:
.backups/txn/<stamp>-<rand>/ holds a copy of every file the save may change
(the content files it writes, every file build.py writes, the files media
stages add, and the sized copies make_derivatives may sweep) and
manifest.json, which says how far the save got:

    prepared     the copies are taken; nothing is written yet
    applied      files are written; the build may be running
    committing   the PostgreSQL store is sending COMMIT (never in JSON mode)
    committed    done; the journal is about to be removed

A journal still there when the admin starts belongs to a save a crash cut
short. For prepared and applied, putting the copies back undoes it. Only the
database can say what a committing journal needs.

Also here: atomic writes, the before-images History lists
(.backups/<name>.<stamp>.json) and the audit.jsonl trail.
"""
import contextlib
import datetime
import fcntl
import json
import os
import secrets
import shutil
import tempfile


def stamp():
    """The time of a save, as its before-images and its journal are named."""
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


def write_manifest(tdir, man):
    atomic_write(tdir / "manifest.json", json.dumps(man, indent=1).encode("utf-8"))


def journal_paths(cfg, content, extra, media):
    """Every file a save must be able to put back, in the order they are
    copied: the content files it writes, what build.py writes, what the
    transaction added with snapshot() and, when media changed, the sized
    copies make_derivatives would sweep."""
    paths = list(content) + cfg.generated_files() + list(extra)
    if media:
        # make_derivatives sweeps sized copies whose original is gone; snapshot
        # them (and so allow their removal) or a save right after a file changed
        # outside the admin would fail on the sweep and not put the copy back.
        from .. import media as media_files
        have = set(paths)
        paths += [o for o in media_files.orphan_copies(cfg) if o not in have]
    return paths


class Journal:
    """One save's journal, opened with its copies taken and its manifest in
    state prepared. man is what the save records about itself: the reason
    and the actor (the PostgreSQL store adds store, txn, xid and stamp)."""

    def __init__(self, cfg, paths, man):
        self.dir = cfg.backups / "txn" / ("%s-%s" % (stamp(), secrets.token_hex(3)))
        self.dir.mkdir(parents=True)
        self.files = []
        for i, p in enumerate(paths):
            if p.exists():
                shutil.copy2(p, self.dir / ("%d.bin" % i))
                self.files.append({"path": str(p), "snap": "%d.bin" % i})
            else:
                self.files.append({"path": str(p), "snap": None})
        self.man = {"state": "prepared"}
        self.man.update(man)
        self.man["files"] = self.files
        write_manifest(self.dir, self.man)

    @property
    def name(self):
        return self.dir.name

    def set_state(self, state, **more):
        self.man["state"] = state
        self.man.update(more)
        write_manifest(self.dir, self.man)

    def restore(self):
        restore(self.files, self.dir)

    def remove(self):
        shutil.rmtree(str(self.dir), ignore_errors=True)


def journals(cfg):
    """The journals left in .backups/txn, oldest first, as (folder, manifest);
    the manifest is None when it cannot be read."""
    out = []
    for m in sorted((cfg.backups / "txn").glob("*/manifest.json")):
        try:
            man = json.loads(m.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            man = None
        out.append((m.parent, man))
    return out


def restore(files, tdir):
    """Put every snapshotted file back exactly; remove files that did not
    exist when the save began."""
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


def write_backup(cfg, name, st, data):
    """The before-image History lists: .backups/<name>.<stamp>.json holds the
    file's bytes from before the save stamped st."""
    (cfg.backups / ("%s.%s.json" % (name, st))).write_bytes(data)


def audit(cfg, entry):
    entry = dict(entry, at=datetime.datetime.now().isoformat(timespec="seconds"))
    with contextlib.suppress(OSError):
        with open(cfg.backups / "audit.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
