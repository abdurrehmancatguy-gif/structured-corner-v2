"""Whole documents: settings, copy, home and navigation.

A PUT sends the whole document back. The server works out which JSON
pointers actually changed and refuses the save if any of them is locked
(payments, tax, cash on delivery), read-only (changed by uploads later) or not
in the schema at all, so a hand-made request cannot slip a change past the UI.
"""
from .. import lint
from .. import schema as schema_mod
from .. import validate
from ..errors import ApiError
from ..routes import DOC, Route
from ..service import enforce, ordered_like, precondition, saved
from .meta import schemas


def _fields(name):
    return schemas()[name]["fields"]


def get_doc(req):
    name = req.params["name"]
    data, rev = req.app.store.doc(name)
    locked = [f["path"] for f in _fields(name) if f.get("locked")]
    return {"name": name, "rev": rev, "data": data, "locked": locked}


def put_doc(req):
    name = req.params["name"]
    body = req.body if isinstance(req.body, dict) else {}
    data = body.get("data")
    if not isinstance(data, dict):
        raise ApiError(400, "bad_request", "Send the document as data.")
    store = req.app.store
    cfg = req.app.cfg
    with store.transaction("edit %s" % name) as txn:
        cur = txn.load(name)
        precondition(req, store.doc(name)[1], cur)
        enforce(_fields(name), cur, data)
        products, _ = store.products()
        ctx = {"icons": schema_mod.icons(cfg), "tints": schema_mod.tints(cfg), "products": products}
        errors, warnings = validate.document(name, data, _fields(name), ctx)
        if errors:
            raise ApiError(422, "validation", "Some fields need attention.", errors)
        new = ordered_like(cur, data)
        txn.put(name, new)
    # Site text that restates a store rule is checked against the rules on
    # either side of the change; it warns and never blocks.
    warnings = warnings + lint.after_save(name, new, store, schemas())
    return saved(req.app, txn, name=name, rev=store.doc(name)[1], data=new, warnings=warnings)


ROUTES = [
    Route("GET", r"documents/" + DOC, get_doc),
    Route("PUT", r"documents/" + DOC, put_doc, body="json"),
]
