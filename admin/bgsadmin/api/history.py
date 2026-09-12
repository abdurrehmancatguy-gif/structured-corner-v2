"""History: every saved version of a product or a document, and restoring one.

Two sources, merged newest first:
- local: the backup every save leaves in flow/content/.backups, the file as
  it was just before that save (<name>.<stamp>.json, the stamp to the
  microsecond; the older second-precision names are read too). A products
  backup is the whole file: it is narrowed to the one product, and backups
  in which that product did not change (a save of another product) are left
  out. Its summary says what the save that replaced it changed.
- git: the versions committed to the repository (gitops), each with what that
  commit changed.

Restoring is a normal save, checked like any other. Fields the admin may not
change (payments, photos, the position) keep today's values and the answer
lists them; keys the old version lacks are filled in (a product's defaults;
for a document, today's values, as a document has no separate defaults); the
result is validated against today's schema and rebuilt. The version it
replaces becomes a backup like any save's, so a restore can be undone too.
"""
import copy
import datetime
import json
import os
import re
import threading

from .. import diff, gitops, validate
from .. import schema as schema_mod
from ..errors import ApiError
from ..routes import Route
from ..service import changed, enforce, field_for, ordered_like, precondition, saved
from ..store.jsonstore import rev_of
from ..validate import MISSING, get
from .meta import schemas
from .products import DEFAULTS

STAMP = r"\d{8}-\d{6}(?:-\d{6})?"
HID = r"(?P<hid>%s|[0-9a-f]{7,40})" % STAMP
BACKUP = re.compile(r"^(?P<name>[a-z0-9_-]+)\.(?P<stamp>%s)\.json$" % STAMP)
PID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SCAN = 300            # newest backups of one file read per request
GIT_MAX = 30          # newest commits of one file read per request
KEEP_LATEST = 50      # pruning never removes a file's newest this many backups

# Backups and commits never change once written, so their parsed JSON is kept.
_CACHE = {}
_CACHE_LOCK = threading.Lock()


class Resource:
    """products/<id> or documents/<name>, checked before anything is read."""

    def __init__(self, value):
        kind, _, key = (value if isinstance(value, str) else "").partition("/")
        if kind == "products" and PID.match(key) and len(key) <= 64:
            self.product, self.file = True, "products"
        elif kind == "documents" and key in schema_mod.document_names():
            self.product, self.file = False, key
        else:
            raise ApiError(400, "bad_request", "Say which product or document: resource=products/<id> or documents/<name>.")
        self.key = key
        self.name = "%s/%s" % (kind, key)
        self.fields = schemas()["products" if self.product else key]["fields"]

    def narrow(self, data):
        if self.product:
            return data.get(self.key) if isinstance(data, dict) else None
        return data

    def diff(self, old, new, ctx):
        if self.product:
            return diff.product(self.key, self.fields, old, new, ctx)
        return diff.document(self.fields, old, new, ctx)


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _cached(key, stamp, load):
    with _CACHE_LOCK:
        hit = _CACHE.get(key)
    if hit is not None and hit[0] == stamp:
        return hit[1]
    data = load()
    with _CACHE_LOCK:
        if len(_CACHE) > 400:
            _CACHE.clear()
        _CACHE[key] = (stamp, data)
    return data


def _read_backup(path):
    st = os.stat(str(path))
    return _cached(str(path), (st.st_mtime_ns, st.st_size), lambda: json.loads(path.read_bytes().decode("utf-8")))


def _read_commit(cfg, sha, rel):
    def load():
        raw = gitops.show_file(cfg, sha, rel)
        return None if raw is None else json.loads(raw.decode("utf-8"))
    return _cached("%s:%s:%s" % (cfg.repo, sha, rel), sha, load)


def _when(stamp):
    """A backup's stamp as local time, or None for a name that is not a date."""
    try:
        return datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S-%f" if stamp.count("-") == 2 else "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def _iso(stamp):
    t = _when(stamp)
    return t.astimezone().isoformat(timespec="seconds") if t else None


def backups(cfg, name=None):
    """[(stamp, path, name)] of the backups in .backups, newest first."""
    d = cfg.backups
    if not d.is_dir():
        return []
    out = []
    with os.scandir(str(d)) as it:
        for e in it:
            m = BACKUP.match(e.name)
            if m and (name is None or m.group("name") == name) and e.is_file(follow_symlinks=False):
                out.append((m.group("stamp"), d / e.name, m.group("name")))
    out.sort(key=lambda x: x[0], reverse=True)
    return out


def _current(req, res):
    store = req.app.store
    if res.product:
        d = store.products()[0].get(res.key)
        return d, (rev_of(d) if d is not None else None)
    return store.doc(res.key)


def _ctx(req):
    return {"products": req.app.store.products()[0]}


def _local_items(cfg, res, current, ctx):
    files = backups(cfg, res.file)
    items, newer = [], current          # newer: the version the save at that stamp wrote
    for stamp, path, _ in files[:SCAN]:
        at = _iso(stamp)
        try:
            data = res.narrow(_read_backup(path))
        except (OSError, ValueError):
            continue
        if at is None or _canon(data) == _canon(newer):
            continue
        items.append({"id": stamp, "source": "local", "at": at, "exists": data is not None,
                      "summary": diff.summary(res.diff(data, newer, ctx))})
        newer = data
    return items, len(files) > SCAN


def _git_items(cfg, res, ctx):
    rel = "flow/content/%s.json" % res.file
    versions = []
    for c in gitops.log_file(cfg, rel, GIT_MAX + 1):
        try:
            versions.append((c, res.narrow(_read_commit(cfg, c["sha"], rel))))
        except ValueError:
            continue
    items = []
    for i, (c, data) in enumerate(versions[:GIT_MAX]):
        older = versions[i + 1][1] if i + 1 < len(versions) else None
        if _canon(data) == _canon(older):
            continue
        items.append({"id": c["sha"], "source": "git", "at": c["at"], "subject": c["subject"], "exists": data is not None,
                      "summary": diff.summary(res.diff(older, data, ctx))})
    return items


def _order(item):
    try:
        return datetime.datetime.fromisoformat(item["at"])
    except (TypeError, ValueError):
        return datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)


def list_history(req):
    res = Resource(req.query.get("resource"))
    cfg = req.app.cfg
    current, rev = _current(req, res)
    ctx = _ctx(req)
    items, more = _local_items(cfg, res, current, ctx)
    git = {"available": gitops.available(cfg), "error": None}
    if git["available"]:
        try:
            items += _git_items(cfg, res, ctx)
        except ApiError as e:
            git["error"] = e.message
    items.sort(key=_order, reverse=True)
    label = ((current or {}).get("name") or res.key) if res.product else schemas()[res.key]["resource"]["label"]
    return {"resource": res.name, "label": label, "exists": current is not None, "current_rev": rev,
            "items": items, "more_local": more, "git": git}


def _version(req, res, hid):
    """One version, narrowed to the resource, and where it came from."""
    cfg = req.app.cfg
    if re.fullmatch(STAMP, hid):
        path = cfg.backups / ("%s.%s.json" % (res.file, hid))
        if _iso(hid) is None or not path.is_file():
            raise ApiError(404, "not_found", "There is no such saved version.")
        try:
            data = _read_backup(path)
        except ValueError:
            raise ApiError(422, "unreadable", "That saved version is not readable.")
        return res.narrow(data), {"id": hid, "source": "local", "at": _iso(hid)}
    c = gitops.commit(cfg, hid) if gitops.available(cfg) else None
    if c is None:
        raise ApiError(404, "not_found", "There is no such commit.")
    try:
        data = _read_commit(cfg, c["sha"], "flow/content/%s.json" % res.file)
    except ValueError:
        raise ApiError(422, "unreadable", "That committed version is not readable.")
    if data is None:
        raise ApiError(404, "not_found", "%s.json did not exist in that commit." % res.file)
    return res.narrow(data), {"id": c["sha"], "source": "git", "at": c["at"], "subject": c["subject"]}


def _esc(k):
    return str(k).replace("~", "~0").replace("/", "~1")


def _fill_doc(new, cur, prefix, filled):
    """A document has no defaults of its own: a key the old version lacks
    keeps today's value, at every level of nesting."""
    for k, v in cur.items():
        if k not in new:
            new[k] = copy.deepcopy(v)
            filled.append(prefix + "/" + _esc(k))
        elif isinstance(v, dict) and isinstance(new[k], dict):
            _fill_doc(new[k], v, prefix + "/" + _esc(k), filled)


def _owner(ptr, chain, blocker):
    """The pointer that keeps today's value (the locked or read-only field's
    own place, or an undescribed key) and the lists (rows) it sits in."""
    segs = ptr.split("/")[1:]
    pos, lists = 0, []
    for g in chain:
        pos += len(g["path"].split("/")) - 1
        if g is blocker:
            return "/" + "/".join(segs[:pos]), lists
        if g["type"] == "rows":
            lists.append("/" + "/".join(segs[:pos]))
            pos += 1
    return "/" + "/".join(segs[:pos + 1]), lists


def _put(obj, ptr, value):
    """Set the value at ptr, or remove it for MISSING. False when the place
    it belongs in does not exist."""
    parts = [p.replace("~1", "/").replace("~0", "~") for p in ptr.split("/")[1:]]
    cur = obj
    for p in parts[:-1]:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        elif isinstance(cur, list) and p.isdigit() and int(p) < len(cur):
            cur = cur[int(p)]
        else:
            return False
    last = parts[-1]
    if isinstance(cur, dict):
        if value is MISSING:
            cur.pop(last, None)
        else:
            cur[last] = copy.deepcopy(value)
        return True
    if isinstance(cur, list) and last.isdigit() and int(last) < len(cur) and value is not MISSING:
        cur[int(last)] = copy.deepcopy(value)
        return True
    return False


def _count(obj, ptr):
    v = get(obj, ptr)
    return len(v) if isinstance(v, list) else 0


def _lower(s):
    return s[:1].lower() + s[1:]


def _plan(res, version, current):
    """What restoring version over current would save: the old version, with
    today's value kept wherever the admin may not make the change, and the
    keys the old version lacks filled in."""
    new = copy.deepcopy(version)
    filled = []
    if res.product:
        for k, v in DEFAULTS.items():
            if k not in new and k in current:
                new[k] = copy.deepcopy(v)
                filled.append("/" + k)
    else:
        _fill_doc(new, current, "", filled)
    kept, seen, blocked = [], set(), None
    for ptr in changed(current, new):
        f, parents = field_for(res.fields, ptr)
        chain = parents + ([f] if f else [])
        blocker = next((g for g in chain if g.get("locked") or g.get("readonly")), None)
        if f is not None and blocker is None:
            continue
        where, lists = _owner(ptr, chain, blocker)
        if where in seen:
            continue
        seen.add(where)
        reason = (blocker.get("locked") or blocker.get("readonly")) if blocker else "It is not something the admin edits."
        # Today's value can only stay if its entry is still there: a version
        # with a different number of slides would add or drop a picture.
        uneven = [p for p in lists if _count(current, p) != _count(new, p)]
        if uneven or not _put(new, where, get(current, where)):
            p = uneven[0] if uneven else where
            what = _lower(blocker["label"]) if blocker else "other data"
            blocked = blocked or ("%s: this version has %d and the site has %d now. Restoring it would add or remove a %s, "
                                  "which cannot be done from here. %s" % (diff.pointer_label(res.fields, p), _count(new, p),
                                                                           _count(current, p), what, reason))
            continue
        kept.append({"path": where, "label": diff.pointer_label(res.fields, where), "reason": reason})
    guarded = set()
    for ptr in changed(current, new):
        f = field_for(res.fields, ptr)[0]
        if f is not None and f.get("guarded"):
            guarded.add(f["path"].strip("/"))
    return {"data": new, "kept": kept, "filled": filled, "guarded": sorted(guarded), "blocked": blocked}


def get_version(req):
    res = Resource(req.query.get("resource"))
    data, meta = _version(req, res, req.params["hid"])
    current, rev = _current(req, res)
    out = dict(meta, resource=res.name, data=data, current_rev=rev, diff=res.diff(data, current, _ctx(req)),
               kept=[], filled=[], guarded=[], blocked=None, same=_canon(data) == _canon(current))
    if data is None:
        out["blocked"] = "The product did not exist in this version."
    elif current is None:
        out["blocked"] = "There is no product with the id %s now. Restoring a deleted product is not possible yet." % res.key
    else:
        plan = _plan(res, data, current)
        out.update(kept=plan["kept"], filled=plan["filled"], guarded=plan["guarded"], blocked=plan["blocked"],
                   same=_canon(plan["data"]) == _canon(current))
    return out


def restore(req):
    body = req.body if isinstance(req.body, dict) else {}
    res = Resource(body.get("resource"))
    confirmed = body.get("confirm_guarded") if isinstance(body.get("confirm_guarded"), list) else []
    version, meta = _version(req, res, req.params["hid"])
    cfg, store = req.app.cfg, req.app.store
    ctx = {"icons": schema_mod.icons(cfg), "tints": schema_mod.tints(cfg)}
    with store.transaction("restore %s" % res.name) as txn:
        if res.product:
            products = txn.load("products")
            cur = products.get(res.key)
            if cur is None:
                raise ApiError(404, "not_found", "There is no product with the id %s now. Restoring a deleted product is not possible yet." % res.key)
            precondition(req, rev_of(cur), cur)
        else:
            cur = txn.load(res.key)
            precondition(req, store.doc(res.key)[1], cur)
        if version is None:
            raise ApiError(409, "cannot_restore", "The product did not exist in that version.")
        plan = _plan(res, version, cur)
        if plan["blocked"]:
            raise ApiError(409, "cannot_restore", plan["blocked"])
        new = ordered_like(cur, plan["data"])
        enforce(res.fields, cur, new, [c for c in confirmed if isinstance(c, str)])
        if res.product:
            errors, warnings = validate.product(res.key, new, products, res.fields, ctx)
        else:
            errors, warnings = validate.document(res.key, new, res.fields, dict(ctx, products=store.products()[0]))
        if errors:
            for e in errors:
                e["label"] = diff.pointer_label(res.fields, e["path"])
            raise ApiError(422, "validation", "This version does not pass today's checks, so it was not restored.", errors)
        if res.product:
            products[res.key] = new
            txn.put("products", products)
        else:
            txn.put(res.key, new)
    rev = rev_of(new) if res.product else store.doc(res.key)[1]
    return saved(req.app, txn, resource=res.name, restored=meta["id"], rev=rev, data=new,
                 kept=plan["kept"], filled=plan["filled"], warnings=warnings)


def backup_stats(req):
    files = backups(req.app.cfg)
    size = 0
    for _, p, _ in files:
        try:
            size += p.stat().st_size
        except OSError:
            pass
    return {"files": len(files), "bytes": size, "oldest": _iso(files[-1][0]) if files else None, "keep_latest": KEEP_LATEST}


def prune(req):
    """Remove backups older than N days, never a file's newest KEEP_LATEST.
    Only the owner asks for this; nothing is ever pruned on its own."""
    days = (req.body if isinstance(req.body, dict) else {}).get("days")
    if isinstance(days, bool) or not isinstance(days, int) or not 1 <= days <= 3650:
        raise ApiError(422, "validation", "Some fields need attention.",
                       [validate.err("/days", "range", "Pick a number of days from 1 to 3650.")])
    cutoff = datetime.datetime.now() - datetime.timedelta(days=days)
    removed = freed = 0
    with req.app.store.transaction("remove old backups"):
        per_file = {}
        for stamp, path, name in backups(req.app.cfg):
            per_file.setdefault(name, []).append((stamp, path))
        for files in per_file.values():
            for stamp, path in files[KEEP_LATEST:]:
                t = _when(stamp)
                if t is None or t >= cutoff:
                    continue
                try:
                    size = path.stat().st_size
                    path.unlink()
                except OSError:
                    continue
                removed += 1
                freed += size
    return dict(backup_stats(req), removed=removed, freed=freed)


ROUTES = [
    Route("GET", r"history", list_history),
    Route("GET", r"history/backups", backup_stats),
    Route("POST", r"history/prune", prune, body="json"),
    Route("GET", r"history/" + HID, get_version),
    Route("POST", r"history/" + HID + r"/restore", restore, body="json"),
]
