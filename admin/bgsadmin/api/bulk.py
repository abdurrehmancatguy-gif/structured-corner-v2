"""Many products at once: the bulk editor's save, and the CSV export and import.

Both saves run the checks a single product save runs (service.enforce, by
way of refusals, and validate.product), and both are all or nothing: one
stale, refused or invalid product stops the whole save, and the answer names
every product that did, so the grid or the import table can mark its rows.

An import is checked first (mode "dry-run") and applied later (mode
"apply") from the plan the check kept in memory: for 30 minutes, and only if
no product changed in between.
"""
import secrets
import threading
import time

from .. import csvio, validate
from .. import access
from ..errors import ApiError
from ..routes import Raw, Route
from ..service import confirm, ordered_like, refusals, saved
from ..store.base import rev_of
from .products import _ctx, _fields

PLAN_TTL = 30 * 60
KEEP_PLANS = 20             # checks nobody applied are dropped oldest first
_plans = {}
_plans_lock = threading.Lock()


def _confirmed(body):
    c = body.get("confirm_guarded") or {}
    if not isinstance(c, dict) or not all(isinstance(v, list) and all(isinstance(x, str) for x in v)
                                          for v in c.values()):
        raise ApiError(400, "bad_request", "confirm_guarded maps a product id to the list of fields confirmed for it.")
    return c


def _guarded(needs):
    labels = {f["path"].strip("/"): f["label"] for f in _fields()}
    names = sorted({labels.get(x, x) for fs in needs.values() for x in fs})
    return ApiError(428, "guarded_field", "Confirm the change to %s for %d product%s." % (
        " and ".join(names), len(needs), "" if len(needs) == 1 else "s"), {"guarded": needs})


def bulk(req):
    body = req.body if isinstance(req.body, dict) else {}
    changes = body.get("changes")
    if not isinstance(changes, list) or not changes or not all(
            isinstance(c, dict) and isinstance(c.get("id"), str) and isinstance(c.get("rev"), str)
            and isinstance(c.get("data"), dict) for c in changes):
        raise ApiError(400, "bad_request", "Send changes as a list of {id, rev, data}, one per product.")
    ids = [c["id"] for c in changes]
    if len(set(ids)) != len(ids):
        raise ApiError(400, "bad_request", "Send each product once.")
    confirmed, fields, ctx = _confirmed(body), _fields(), _ctx(req)
    with req.app.store.transaction("bulk edit") as txn:
        products = txn.load("products")
        stale = [{"id": c["id"], "current_rev": rev_of(products[c["id"]]) if c["id"] in products else None}
                 for c in changes if c["id"] not in products or rev_of(products[c["id"]]) != c["rev"]]
        if stale:
            raise ApiError(412, "stale_rev", "Some products changed since you opened them. Reload those rows.",
                           {"conflicts": stale})
        errors, needs, warnings = {}, {}, {}
        for c in changes:
            pid = c["id"]
            # a stock-only role is held to stock here too, row by row: the
            # grid is a different screen, not a different rule (access.py)
            access.check_product_write(req.role, c["data"], products[pid])
            need, refused = refusals(fields, products[pid], c["data"], confirmed.get(pid, []))
            found, notes = validate.product(pid, c["data"], products, fields, ctx)
            if refused or found:
                errors[pid] = refused + found
            if need:
                needs[pid] = need
            if notes:
                warnings[pid] = notes
        if errors:
            raise ApiError(422, "validation", "Some products need attention.", {"errors": errors})
        if needs:
            raise _guarded(needs)
        for c in changes:
            new = ordered_like(products[c["id"]], c["data"])
            confirm(txn, c["id"], fields, products[c["id"]], new, confirmed.get(c["id"], []))
            products[c["id"]] = new
        txn.put("products", products)
    return saved(req.app, txn, revs={pid: rev_of(products[pid]) for pid in ids}, warnings=warnings)


def export(req):
    products, _ = req.app.store.products()
    ids = [i.strip() for i in (req.query.get("ids") or "").split(",") if i.strip()]
    missing = [i for i in ids if i not in products]
    if missing:
        raise ApiError(404, "not_found", "There is no product with the id %s." % ", ".join(missing[:5]))
    chosen = sorted(set(ids) or set(products), key=lambda pid: (products[pid].get("order", 0), pid))
    return Raw(csvio.export([(pid, products[pid]) for pid in chosen]), "text/csv; charset=utf-8",
               {"Content-Disposition": 'attachment; filename="bgs-products.csv"'})


def import_products(req):
    body = req.body if isinstance(req.body, dict) else {}
    if body.get("mode") == "dry-run":
        return _check(req, body)
    if body.get("mode") == "apply":
        return _apply(req, body)
    raise ApiError(400, "bad_request", "Send mode dry-run to check a file, or apply with the plan_id of a check.")


def _sweep():
    now = time.time()
    for k in [k for k, p in _plans.items() if now - p["at"] > PLAN_TTL]:
        del _plans[k]


def _check(req, body):
    text = body.get("csv")
    if not isinstance(text, str):
        raise ApiError(400, "bad_request", "Send the file's text as csv.")
    products, base = req.app.store.products()
    p = csvio.plan(text, products, _fields(), _ctx(req), req.app.cfg.assets / "img")
    plan = {"id": secrets.token_urlsafe(16), "at": time.time(), "base_rev": base,
            "planned": p["planned"], "needs": p["needs"], "errors": p["errors"]}
    with _plans_lock:
        _sweep()
        while len(_plans) >= KEEP_PLANS:
            del _plans[min(_plans, key=lambda k: _plans[k]["at"])]
        _plans[plan["id"]] = plan
    counts = {a: sum(r["action"] == a for r in p["rows"]) for a in ("create", "update", "unchanged", "error")}
    return {"plan_id": plan["id"], "base_rev": base, "rows": p["rows"], "counts": counts,
            "needs_confirm": p["needs"], "ignored_columns": p["ignored"], "expires_in": PLAN_TTL}


def _apply(req, body):
    wanted = body.get("plan_id")
    with _plans_lock:
        _sweep()
        plan = _plans.get(wanted) if isinstance(wanted, str) else None
    if plan is None:
        raise ApiError(404, "plan_not_found", "That check has expired or was already applied. Check the file again.")
    if plan["errors"]:
        raise ApiError(422, "plan_has_errors", "Fix the rows with errors in the file, then check it again.",
                       {"error_rows": plan["errors"]})
    confirmed = _confirmed(body)
    missing = {p: [f for f in fs if f not in confirmed.get(p, [])] for p, fs in plan["needs"].items()}
    missing = {p: fs for p, fs in missing.items() if fs}
    if missing:
        raise _guarded(missing)
    store = req.app.store
    with store.transaction("CSV import") as txn:
        products = txn.load("products")
        current = store.products()[1]
        if current != plan["base_rev"]:
            raise ApiError(412, "stale_rev", "Products changed since the file was checked. Check it again.",
                           {"current_rev": current})
        fields = _fields()
        for p, (action, new) in plan["planned"].items():
            merged = ordered_like(products[p], new) if action == "update" else new
            confirm(txn, p, fields, products.get(p) or {}, merged, confirmed.get(p, []))
            products[p] = merged
        txn.put("products", products)
    with _plans_lock:
        _plans.pop(plan["id"], None)
    done = plan["planned"]
    return saved(req.app, txn, revs={p: rev_of(products[p]) for p in done},
                 created=[p for p, (a, _) in done.items() if a == "create"],
                 updated=[p for p, (a, _) in done.items() if a == "update"])


ROUTES = [
    Route("POST", r"products/bulk", bulk, body="json"),
    Route("GET", r"products/export\.csv", export),
    Route("POST", r"products/import", import_products, body="json", limit=6 * 1024 * 1024),
]
