"""Collections: the four categories and the unfiltered page, each edited as one.

A collection's words live in three documents: its name, breadcrumb name and
intro in copy.json, its circle in navigation.json (the entry that links to
collection.html?cat=<key>), and its homepage shelf in home.json. The screen
edits them as one view, and a save writes every document it touches in one
transaction, so the shop never shows a new name beside an old heading. The
view's rev covers only what the view holds: a save elsewhere in those
documents (the banner, the footer) never makes a collection stale. Which
products belong and in what order is the products' own data, changed with
products/reorder.
"""
import copy

from .. import lint
from .. import schema as schema_mod
from .. import validate
from ..errors import ApiError
from ..routes import Route
from ..schema.copy import COLLECTIONS
from ..schema.home import SHELVES
from ..service import changed, enforce, field_for, precondition, saved
from ..store.jsonstore import rev_of
from .meta import schemas

KEY = r"(?P<key>%s)" % "|".join(k for k, _ in COLLECTIONS)
NAMES = dict(COLLECTIONS)
SHELF_OF = {cat: sid for sid, _, cat, _ in SHELVES if cat}
DOCS = ("copy", "home", "navigation")


def href(key):
    return "collection.html" if key == "all" else "collection.html?cat=" + key


def nav_index(nav, key):
    """The category bar entry that opens this collection, or None. The
    unfiltered page has no circle of its own."""
    if key == "all":
        return None
    for i, c in enumerate(nav.get("categories") or []):
        if isinstance(c, dict) and c.get("href") == href(key):
            return i
    return None


def places(key, docs):
    """Each pointer in the view, and the document and pointer it is kept at."""
    out = {"/label": ("copy", "/categories/%s/label" % key),
           "/crumb": ("copy", "/categories/%s/crumb" % key),
           "/intro": ("copy", "/collection_intros/%s" % key)}
    i = nav_index(docs["navigation"], key)
    if i is not None:
        for part in ("label", "tint", "cutout", "image"):
            out["/circle/" + part] = ("navigation", "/categories/%d/%s" % (i, part))
    sid = SHELF_OF.get(key)
    if sid:
        out["/shelf/heading"] = ("home", "/sections/" + sid)
        out["/shelf/limit"] = ("home", "/shelves/%s/limit" % sid)
        out["/shelf/link_label"] = ("home", "/shelves/%s/link_label" % sid)
    return out


def view(key, docs):
    """What the collection screen edits, read out of the three documents. A
    collection with no circle or no shelf has null there, so the screen can
    say so instead of offering fields that would do nothing."""
    out = {"circle": None, "shelf": None}
    for vp, (doc, ptr) in places(key, docs).items():
        parts = vp.strip("/").split("/")
        holder = out
        if len(parts) == 2:
            if out[parts[0]] is None:
                out[parts[0]] = {}
            holder = out[parts[0]]
        v = validate.get(docs[doc], ptr)
        if v is not validate.MISSING:
            holder[parts[-1]] = copy.deepcopy(v)
    return out


def _walk(obj, ptr):
    """The container that holds ptr's last part, and that part. Missing
    objects on the way are created, so an older file gains the new keys."""
    parts = ptr.strip("/").split("/")
    for p in parts[:-1]:
        obj = obj[int(p)] if isinstance(obj, list) else obj.setdefault(p, {})
    return obj, (int(parts[-1]) if isinstance(obj, list) else parts[-1])


def apply(docs, where, cur, new):
    """Copies of the documents the change touches, with it written in. A
    pointer the view does not hold is refused, like any unknown field."""
    out = {}
    for vp in changed(cur, new):
        if vp not in where:
            raise ApiError(403, "not_editable", "That part of the collection cannot be changed here.", {"path": vp})
        doc, ptr = where[vp]
        target = out.setdefault(doc, copy.deepcopy(docs[doc]))
        holder, last = _walk(target, ptr)
        v = validate.get(new, vp)
        if v is validate.MISSING:
            if isinstance(holder, dict):
                holder.pop(last, None)
        else:
            holder[last] = copy.deepcopy(v)
    return out


def _docs(store):
    return {d: store.doc(d)[0] for d in DOCS}


def _counts(key, products):
    """Published and draft products in the collection, counted the way
    build.py counts them for a shelf's {n}."""
    rows = [d for d in products.values() if key == "all" or d.get("category") == key]
    live = sum(1 for d in rows if d.get("published", True))
    return live, len(rows) - live


def _shelf_shows(v, live):
    """How many cards the homepage shelf draws and what its link reads."""
    s = v.get("shelf")
    if not s:
        return None
    limit = s.get("limit")
    whole = isinstance(limit, int) and not isinstance(limit, bool)
    return {"cards": min(limit, live) if whole else live,
            "link": str(s.get("link_label") or "").replace("{n}", str(live))}


def _item(key, docs, products):
    v = view(key, docs)
    live, drafts = _counts(key, products)
    return {"key": key, "name": NAMES[key], "href": href(key), "rev": rev_of(v), "data": v,
            "published": live, "drafts": drafts, "shelf_shows": _shelf_shows(v, live)}


def fields(key, docs):
    """The schema field behind each pointer of the view, moved to that
    pointer, so the screen draws them the way it draws any document."""
    out = []
    for vp, (doc, ptr) in places(key, docs).items():
        f, _ = field_for(schemas()[doc]["fields"], ptr)
        if f:
            out.append(dict(f, path=vp))
    return out


def list_collections(req):
    store = req.app.store
    docs = _docs(store)
    products, crev = store.products()
    return {"collection_rev": crev, "items": [_item(k, docs, products) for k, _ in COLLECTIONS]}


def get_collection(req):
    store = req.app.store
    key = req.params["key"]
    docs = _docs(store)
    products, crev = store.products()
    return dict(_item(key, docs, products), fields=fields(key, docs), collection_rev=crev)


def put_collection(req):
    key = req.params["key"]
    body = req.body if isinstance(req.body, dict) else {}
    data = body.get("data")
    if not isinstance(data, dict):
        raise ApiError(400, "bad_request", "Send the collection as data.")
    store = req.app.store
    cfg = req.app.cfg
    sch = schemas()
    with store.transaction("edit collection %s" % key) as txn:
        docs = {d: txn.load(d) for d in DOCS}
        where = places(key, docs)
        cur = view(key, docs)
        precondition(req, rev_of(cur), cur)
        back = {v: k for k, v in where.items()}
        new_docs = apply(docs, where, cur, data)
        products, _ = store.products()
        ctx = {"icons": schema_mod.icons(cfg), "tints": schema_mod.tints(cfg), "products": products}
        errors = []
        for doc, new in new_docs.items():
            # Each document's own schema still decides what may change, so a
            # locked or read-only field (the circle's picture) refuses here
            # exactly as it does in the document's own editor.
            try:
                enforce(sch[doc]["fields"], docs[doc], new)
            except ApiError as e:
                if isinstance(e.details, dict) and (doc, e.details.get("path")) in back:
                    e.details["path"] = back[(doc, e.details["path"])]
                raise
            errs, _ = validate.document(doc, new, sch[doc]["fields"], ctx)
            errors += [dict(x, path=back.get((doc, x["path"]), x["path"]), document=doc) for x in errs]
        if errors:
            raise ApiError(422, "validation", "Some fields need attention.", errors)
        for doc, new in new_docs.items():
            txn.put(doc, new)
    # Site text that restates a store rule is checked as on any copy save.
    warnings = lint.after_save("copy", new_docs["copy"], store, sch) if "copy" in new_docs else []
    now = view(key, _docs(store))
    return saved(req.app, txn, key=key, rev=rev_of(now), data=now, warnings=warnings)


ROUTES = [
    Route("GET", r"collections", list_collections),
    Route("GET", r"collections/" + KEY, get_collection),
    Route("PUT", r"collections/" + KEY, put_collection, body="json"),
]
