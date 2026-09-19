"""The storage interface every store implements, as the admin uses it.

build.py keeps reading flow/content/*.json, now and after PostgreSQL: those
files are the build input and, in git, the record of what went live. A store
is the editing side of that. The JSON store edits those files directly; the
PostgreSQL store keeps the content in the database and writes the same files
from it on every save, before the build. Validation, locked fields and
referential checks live above the store (validate.py, service.py and the API
modules), so both stores apply the same rules; the database adds its own.

The ContentStore, held as app.store:
    actor                    who saves: the signed-in person, else this computer's user
    open()                -> [journal, ...]  take the admin's lock, settle the saves a crash cut
                                             short (recover()), sweep stray temporary files and
                                             prime the reads; SystemExit while another admin
                                             holds the lock
    recover()             -> [journal, ...]  the interrupted saves it settled
    close()                                  let go of the lock (and any connection)
    doc(name)             -> (data, rev)     a deep copy of a document
    products()            -> (dict, rev)     every product in file order, and the collection rev
    product(pid)          -> (data, rev)     404 ApiError "There is no product with the id %s."
    external_changes()    -> [name, ...]     changed outside the admin, in content_names() order
    acknowledge()                            the owner has seen them ("Got it")
    busy()                -> reason or None  what the save in progress is doing
    transaction(reason)   -> Txn             one writer at a time: 423 busy at once, without
                                             waiting, while another save holds the lock
    export_snapshot()     -> {name: bytes}   every content file as the store holds it, in
                                             content_names() order, drafts included

A Txn, inside `with store.transaction(reason) as txn:`
    load(name)                               a private, mutable copy of what was saved before the
                                             transaction began; the same object on every call
    put(name, data)                          stage a whole document (for products, the whole dict)
    snapshot(path)                           one more file a failed save must put back
    add_file(path, src), remove_file(path)   media placed or taken away once the copies are taken
    run_tool(name)                           a tool from tools.TOOLS to run after make_derivatives
    confirm(pid, field)                      the owner confirmed changing this guarded field
    force                                    build even with nothing to write ("Rebuild now")
    result                                   after the block: {"changed": [], "build": None} when
                                             nothing was written, otherwise {"changed": [names],
                                             "build": {"ok": True, "ms": ..., "problems": []}}

What callers rely on, and every store honours:
- Reads made inside the block (store.doc, store.products) see the state from
  before the transaction; preconditions are checked against it. Reads made
  after the block see the new state.
- One transaction may put several documents (a collection saves copy, home
  and navigation) and read every one (trash, restore). They commit or fail
  together, with one build.
- An exception inside the block writes nothing and propagates: that is how
  validation, 412 and 409 answers stop a save. A normal exit commits: the
  files are written atomically and the site is rebuilt, and a build that
  fails puts every file back byte for byte and raises 422 build_failed.
- A transaction with nothing staged is only a lock (publish, prune).
- Contention is always ApiError code "busy": the reel job retries on it.

Revs are 16 hex characters of sha256 over the canonical JSON (rev_of), the
same in every store, and are only ever compared for equality. A document's
rev is the hash of its file's bytes, which is rev_of(data) for a file in
canonical form.
"""
import contextlib
import hashlib
import os
import pathlib
import re
import threading

from .. import schema, tools
from ..jsonutil import canonical
from . import files

# Who is saving, for the length of one request. The server is threaded and one
# store object serves every request, so the signed-in person cannot be kept on
# the store itself: two people saving at once would overwrite each other's
# name in the audit trail. httpd sets this around each handler; the stores read
# it when they write a journal, an audit row or a revision, and fall back to
# the machine's own user when nobody is signed in (this Mac, no login asked).
_acting = threading.local()


def acting_as(actor):
    """Use as a context manager: with acting_as("someone@example.com"): ..."""
    return _Acting(actor)


class _Acting:
    def __init__(self, actor):
        self.actor = actor
        self.before = None

    def __enter__(self):
        self.before = getattr(_acting, "actor", None)
        _acting.actor = self.actor
        return self

    def __exit__(self, *exc):
        _acting.actor = self.before
        return False


def actor_now(default):
    return getattr(_acting, "actor", None) or default


def sha(b):
    return hashlib.sha256(b).hexdigest()


def rev_of(obj):
    return sha(canonical(obj))[:16]


def content_names():
    """products, then every document in the admin's order: what a store holds
    and what export_snapshot() returns."""
    return ("products",) + tuple(schema.document_names())


class ContentStore:
    """What app.store offers; the module docstring has the contract. Beside
    it, for server.py's start lines: describe() says what holds the
    content, warnings() what the owner should fix, and kept lists the
    journals recover() finished rather than rolled back (only the database
    can have kept a save)."""
    actor = None
    kept = ()

    def describe(self):
        return "JSON files in flow/content"

    def warnings(self):
        return []

    def open(self):
        raise NotImplementedError

    def recover(self):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def doc(self, name):
        raise NotImplementedError

    def products(self):
        raise NotImplementedError

    def product(self, pid):
        raise NotImplementedError

    def external_changes(self):
        raise NotImplementedError

    def acknowledge(self):
        raise NotImplementedError

    def busy(self):
        raise NotImplementedError

    def transaction(self, reason):
        raise NotImplementedError

    def export_snapshot(self):
        raise NotImplementedError


class Failed(Exception):
    """The build, or a tool it needs, refused the change: the save is undone."""

    def __init__(self, problems):
        super().__init__("; ".join(problems))
        self.problems = problems


class CannotStart(Exception):
    """A store, or dbtool, will not start: one plain sentence for the terminal
    and the exit status, 2 when it refuses (a bad setting, the wrong
    database, another admin running) and 3 when the database is not
    answering. Nothing has been changed when it is raised."""

    def __init__(self, message, status=2):
        super().__init__(message)
        self.message = message
        self.status = status


# "<product id>/<field>", the form the database's never_discount guard reads
CONFIRMED = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*/[a-z_]+")


class Txn:
    """What every store's transaction shares: staging, the file calls, the
    confirmed fields, and the media and build steps of a commit. Each store
    adds load() and commit()."""

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
        self.confirmed = []       # "<id>/<field>": guarded changes the owner confirmed
        self.result = None

    def load(self, name):
        raise NotImplementedError

    def commit(self):
        raise NotImplementedError

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

    def confirm(self, pid, field):
        """The owner confirmed changing the guarded field of product pid in
        this save. The API modules call it once service.enforce has let the
        change through (service.confirm); the PostgreSQL store hands the list
        to the database, whose own guard refuses a never_discount change
        nobody confirmed. Anything but an id and a field name is refused, so
        nothing else can get into that list."""
        key = "%s/%s" % (pid, field) if isinstance(pid, str) and isinstance(field, str) else None
        if key is None or not CONFIRMED.fullmatch(key):
            raise ValueError("Not a product id and a field name: %r, %r" % (pid, field))
        if key not in self.confirmed:
            self.confirmed.append(key)

    # ---- the file side of a commit, the same in every store --------------------

    def place_media(self):
        """Put the media this save made in place, and take away what it removed."""
        for dst, src in self.files:
            files.atomic_write(dst, src.read_bytes())
        for p in self.removed:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(p)

    def build(self, paths, before):
        """make_derivatives and the tools when media changed, then build.py,
        then the check that nothing moved but the journaled files (and what
        media may change). paths are the journaled files, before is
        tools.scan() from before the writes. Returns build.py's result;
        raises Failed."""
        cfg = self.cfg
        if self.media:
            for name in ["derivatives"] + self.tools:
                d = tools.run(cfg, name)
                if not d["ok"]:
                    raise Failed(d["problems"])
        build = tools.run(cfg, "build")
        if not build["ok"]:
            raise Failed(build["problems"])
        allowed = {os.path.relpath(str(p), str(cfg.flow)) for p in paths}
        odd = tools.unexpected(before, tools.scan(cfg.flow), allowed if not self.media else allowed | self.media_allowed())
        if odd:
            raise Failed(["The build changed files it should not have: %s" % ", ".join(odd[:6])])
        return build

    def media_allowed(self):
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
