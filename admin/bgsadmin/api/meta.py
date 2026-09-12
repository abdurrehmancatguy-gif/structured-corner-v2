"""Session, schema, status and "Rebuild now"."""
import sys

from .. import schema as schema_mod
from ..config import PAGES
from ..routes import Route
from ..service import saved

_SCHEMAS = None


def schemas():
    global _SCHEMAS
    if _SCHEMAS is None:
        _SCHEMAS = schema_mod.load()
    return _SCHEMAS


def session(req):
    app = req.app
    return {"python": sys.version.split()[0], "pillow": app.probes.get("pillow"),
            "ffmpeg": bool(app.probes.get("ffmpeg")), "no_push": app.cfg.no_push,
            "actor": app.store.actor, "build": app.build, "recovered": app.recovered}


def get_schema(req):
    cfg = req.app.cfg
    return {"resources": schemas(), "icons": schema_mod.icons(cfg), "tints": schema_mod.tints(cfg),
            "pages": list(PAGES)}


def status(req):
    store = req.app.store
    revs = {"products": store.products()[1]}
    for n in schema_mod.document_names():
        revs[n] = store.doc(n)[1]
    return {"revs": revs, "external": store.external_changes(), "busy": store.busy(), "build": req.app.build}


def acknowledge(req):
    req.app.store.acknowledge()
    return status(req)


def rebuild(req):
    with req.app.store.transaction("rebuild") as txn:
        txn.force = True
    return saved(req.app, txn)


ROUTES = [
    Route("GET", r"session", session),
    Route("GET", r"schema", get_schema),
    Route("GET", r"status", status),
    Route("POST", r"status/ack", acknowledge, body="json"),
    Route("POST", r"build", rebuild, body="json"),
]
