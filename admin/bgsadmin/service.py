"""Helpers the API modules share: which JSON pointers a change touches, whether
each one may be changed, and the precondition on the document's rev."""
import copy

from .errors import ApiError

_MISSING = object()


def _esc(k):
    return str(k).replace("~", "~0").replace("/", "~1")


def flatten(obj, prefix="", out=None):
    out = {} if out is None else out
    if isinstance(obj, dict) and obj:
        for k, v in obj.items():
            flatten(v, prefix + "/" + _esc(k), out)
    elif isinstance(obj, list) and obj:
        for i, v in enumerate(obj):
            flatten(v, "%s/%d" % (prefix, i), out)
    else:
        out[prefix or "/"] = obj
    return out


def changed(old, new):
    a, b = flatten(old), flatten(new)
    return sorted(k for k in set(a) | set(b) if a.get(k, _MISSING) != b.get(k, _MISSING))


def field_for(fields, ptr):
    """The schema field that owns ptr (the most specific one), or None.
    Inside a rows field, the item's own field owns it."""
    best = None
    for f in fields:
        p = f["path"]
        if (ptr == p or ptr.startswith(p + "/")) and (best is None or len(p) > len(best["path"])):
            best = f
    if best is None:
        return None, []
    rest = ptr[len(best["path"]):]
    if best["type"] == "rows" and rest:
        parts = rest.split("/", 2)
        sub = "/" + parts[2] if len(parts) > 2 else ""
        if not sub:
            return best, []
        inner, parents = field_for(best.get("fields", []), sub)
        return inner, [best] + parents
    return best, []


def enforce(fields, old, new, confirmed=()):
    """Refuse a change to anything locked, read-only or not in the schema.
    A locked field refuses even when the whole document is sent back."""
    for ptr in changed(old, new):
        f, parents = field_for(fields, ptr)
        chain = parents + ([f] if f else [])
        if f is None:
            raise ApiError(403, "not_editable", "That part of the content cannot be changed from the admin.", {"path": ptr})
        for g in chain:
            if g.get("locked"):
                raise ApiError(403, "locked_field", g["locked"], {"path": ptr, "field": g["path"]})
            if g.get("readonly"):
                raise ApiError(403, "not_editable", g["readonly"], {"path": ptr, "field": g["path"]})
        if f.get("guarded") and f["path"].strip("/") not in confirmed:
            raise ApiError(428, "guarded_field", "Confirm the change to %s." % f["label"], {"path": ptr, "field": f["path"]})


def refusals(fields, old, new, confirmed=()):
    """Everything enforce() would refuse in one change, not only the first
    thing, for saves that answer per product (bulk edit, CSV import). Each
    refused top-level field is put back as it was and the check runs again.
    Returns (the guarded fields still to confirm, the refusals as errors)."""
    need, errors = [], []
    trial = copy.deepcopy(new)
    while True:
        try:
            enforce(fields, old, trial, list(confirmed) + need)
            return need, errors
        except ApiError as e:
            d = e.details or {}
            if e.code == "guarded_field" and d.get("field", "").strip("/") not in need:
                need.append(d["field"].strip("/"))
                continue
            errors.append({"path": d.get("path", ""), "code": e.code, "message": e.message})
            parts = (d.get("path") or "").split("/")
            if len(parts) < 2 or not isinstance(trial, dict) or not isinstance(old, dict):
                return need, errors
            key = parts[1].replace("~1", "/").replace("~0", "~")
            if trial.get(key, _MISSING) == old.get(key, _MISSING):
                return need, errors
            if key in old:
                trial[key] = copy.deepcopy(old[key])
            else:
                del trial[key]


def precondition(req, current_rev, current):
    want = req.if_match()
    if not want:
        raise ApiError(428, "rev_required", "Reload and try again: the save did not say which version it was editing.")
    if want != current_rev:
        raise ApiError(412, "stale_rev", "This changed since you opened it.", {"current_rev": current_rev, "current": current})


def ordered_like(old, new):
    """Keep the keys in the order the file already has, so a save's diff shows
    only the values that changed. New keys go at the end."""
    if isinstance(old, dict) and isinstance(new, dict):
        out = {k: ordered_like(old[k], new[k]) for k in old if k in new}
        out.update({k: v for k, v in new.items() if k not in old})
        return out
    if isinstance(old, list) and isinstance(new, list):
        return [ordered_like(old[i], v) if i < len(old) else v for i, v in enumerate(new)]
    return new


def saved(app, txn, **extra):
    build = txn.result["build"] if txn.result else None
    app.note_build(build)
    out = {"build": build, "changed": txn.result["changed"] if txn.result else []}
    out.update(extra)
    return out
