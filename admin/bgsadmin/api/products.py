"""Products: list, read, create, edit, duplicate, delete, reorder.

Every change is checked against the product schema (nothing locked, read-only
or unknown may change), validated, and saved in a transaction that rebuilds
the site, so the preview shows it at once or nothing changes at all.
"""
import copy
import urllib.parse

from .. import schema as schema_mod
from .. import validate
from ..errors import ApiError
from ..routes import ID, Route
from ..service import enforce, ordered_like, precondition, saved
from ..store.jsonstore import rev_of
from .meta import schemas

# The key order the file already uses, so a new product reads like the others.
TEMPLATE = ["name", "category", "price", "sizes", "size", "contents", "gender", "stock", "top", "heart", "base",
            "ingredients", "barcode", "story", "never_discount", "published", "order", "images", "name_ar",
            "story_ar", "family", "tone", "occasion", "season", "longevity", "sillage", "badge", "seo_title",
            "seo_description", "image_alt", "related"]
DEFAULTS = {"stock": None, "story": [], "never_discount": False, "published": False, "images": [], "name_ar": "",
            "story_ar": [], "family": "", "tone": "", "occasion": "", "season": "", "longevity": "", "sillage": "",
            "badge": "", "seo_title": "", "seo_description": "", "image_alt": "", "related": []}


def _fields():
    return schemas()["products"]["fields"]


def _ctx(req):
    cfg = req.app.cfg
    return {"icons": schema_mod.icons(cfg), "tints": schema_mod.tints(cfg), "img_dir": cfg.assets / "img"}


def _mentions(href, pid):
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(href or "").query)
    return pid in q.get("p", [])


def refs(pid, products, docs):
    """Where the product appears, so a delete can say what it would break."""
    out = []
    home = docs.get("home", {})
    for i, s in enumerate(home.get("hero_slides", [])):
        if any(_mentions((s.get(k) or {}).get("href"), pid) for k in ("primary", "secondary")):
            out.append({"where": "Homepage banner, slide %d" % (i + 1), "link": "#/content/home"})
    for i, r in enumerate((home.get("reels") or {}).get("items", [])):
        if r.get("product") == pid:
            out.append({"where": "Homepage films, film %d" % (i + 1), "link": "#/content/home"})
    nav = docs.get("navigation", {})
    for key, label in (("categories", "Category bar"), ("tabs", "Phone tab bar")):
        for i, e in enumerate(nav.get(key, [])):
            if _mentions(e.get("href"), pid):
                out.append({"where": "%s, entry %d" % (label, i + 1), "link": "#/content/navigation"})
    for col in nav.get("footer", []):
        for e in col.get("links", []):
            if _mentions(e.get("href"), pid):
                out.append({"where": "Footer, %s" % col.get("heading", ""), "link": "#/content/navigation"})
    for other, d in products.items():
        if other != pid and pid in (d.get("related") or []):
            out.append({"where": "Related products of %s" % d.get("name", other), "link": "#/products/%s" % other})
    return out


def list_products(req):
    products, crev = req.app.store.products()
    q = (req.query.get("q") or "").strip().lower()
    cat, status = req.query.get("category"), req.query.get("status")
    items = []
    for pid, d in products.items():
        active = d.get("published", True) is not False
        if cat and d.get("category") != cat:
            continue
        if status == "active" and not active or status == "draft" and active:
            continue
        if q and q not in pid and q not in (d.get("name") or "").lower():
            continue
        items.append({"id": pid, "rev": rev_of(d), "data": d})
    items.sort(key=lambda it: (it["data"].get("order", 0), it["id"]))
    return {"collection_rev": crev, "items": items}


def get_product(req):
    store = req.app.store
    pid = req.params["id"]
    data, rev = store.product(pid)
    products, _ = store.products()
    docs = {n: store.doc(n)[0] for n in schema_mod.document_names()}
    return {"id": pid, "rev": rev, "data": data, "refs": refs(pid, products, docs)}


def put_product(req):
    pid = req.params["id"]
    body = req.body if isinstance(req.body, dict) else {}
    data = body.get("data")
    if not isinstance(data, dict):
        raise ApiError(400, "bad_request", "Send the product's fields as data.")
    confirmed = body.get("confirm_guarded") or []
    with req.app.store.transaction("edit %s" % pid) as txn:
        products = txn.load("products")
        if pid not in products:
            raise ApiError(404, "not_found", "There is no product with the id %s." % pid)
        cur = products[pid]
        precondition(req, rev_of(cur), cur)
        enforce(_fields(), cur, data, confirmed)
        errors, warnings = validate.product(pid, data, products, _fields(), _ctx(req))
        if errors:
            raise ApiError(422, "validation", "Some fields need attention.", errors)
        new = ordered_like(cur, data)
        products[pid] = new
        txn.put("products", products)
    return saved(req.app, txn, id=pid, rev=rev_of(new), data=new, warnings=warnings)


def create_product(req):
    body = req.body if isinstance(req.body, dict) else {}
    pid, data = body.get("id"), body.get("data")
    if not isinstance(data, dict):
        raise ApiError(400, "bad_request", "Send the new product's fields as data.")
    editable = {f["path"].strip("/") for f in _fields() if not f.get("readonly") and not f.get("locked")}
    unknown = [k for k in data if k not in editable]
    if unknown:
        raise ApiError(400, "bad_request", "These fields cannot be set on a new product: %s." % ", ".join(unknown))
    with req.app.store.transaction("create %s" % pid) as txn:
        products = txn.load("products")
        problem = validate.product_id_problem(pid, products)
        if problem:
            raise ApiError(422, "validation", "Pick another id.", [validate.err("/id", "id", problem)])
        merged = dict(DEFAULTS, **data)
        merged["order"] = max([d.get("order", 0) for d in products.values()] + [0]) + 1
        new = {k: merged[k] for k in TEMPLATE if k in merged}
        errors, warnings = validate.product(pid, new, products, _fields(), _ctx(req))
        if errors:
            raise ApiError(422, "validation", "Some fields need attention.", errors)
        products[pid] = new
        txn.put("products", products)
    return 201, saved(req.app, txn, id=pid, rev=rev_of(new), data=new, warnings=warnings)


def duplicate_product(req):
    pid = req.params["id"]
    body = req.body if isinstance(req.body, dict) else {}
    new_id = body.get("new_id")
    with req.app.store.transaction("duplicate %s" % pid) as txn:
        products = txn.load("products")
        if pid not in products:
            raise ApiError(404, "not_found", "There is no product with the id %s." % pid)
        problem = validate.product_id_problem(new_id, products)
        if problem:
            raise ApiError(422, "validation", "Pick another id.", [validate.err("/new_id", "id", problem)])
        new = copy.deepcopy(products[pid])
        new["name"] = body.get("name") or (new.get("name", "") + " copy")[:60]
        new["images"] = []
        new["published"] = False
        new["order"] = max(d.get("order", 0) for d in products.values()) + 1
        if "barcode" in new:
            new["barcode"] = ""
        errors, warnings = validate.product(new_id, new, products, _fields(), _ctx(req))
        if errors:
            raise ApiError(422, "validation", "Some fields need attention.", errors)
        products[new_id] = new
        txn.put("products", products)
    return 201, saved(req.app, txn, id=new_id, rev=rev_of(new), data=new, warnings=warnings)


def delete_product(req):
    pid = req.params["id"]
    with req.app.store.transaction("delete %s" % pid) as txn:
        products = txn.load("products")
        if pid not in products:
            raise ApiError(404, "not_found", "There is no product with the id %s." % pid)
        cur = products[pid]
        precondition(req, rev_of(cur), cur)
        found = refs(pid, products, {n: txn.load(n) for n in schema_mod.document_names()})
        if found:
            raise ApiError(409, "referenced", "Take it out of these places first.", {"refs": found})
        del products[pid]
        txn.put("products", products)
    return saved(req.app, txn, id=pid, deleted=True, files_left=cur.get("images", []))


def reorder(req):
    body = req.body if isinstance(req.body, dict) else {}
    cat, ids = body.get("category"), body.get("ids")
    store = req.app.store
    with store.transaction("reorder %s" % cat) as txn:
        products = txn.load("products")
        crev = store.products()[1]
        if body.get("expect_collection_rev") != crev:
            raise ApiError(412, "stale_rev", "The product list changed since you opened it.", {"current_rev": crev})
        members = [p for p, d in products.items() if d.get("category") == cat]
        if not isinstance(ids, list) or sorted(ids) != sorted(members):
            raise ApiError(422, "validation", "Send every product of the category, once each.")
        orders = sorted(products[p].get("order", 0) for p in members)
        for p, o in zip(ids, orders):
            products[p]["order"] = o
        txn.put("products", products)
    return saved(req.app, txn, collection_rev=store.products()[1])


ROUTES = [
    Route("GET", r"products", list_products),
    Route("POST", r"products", create_product, body="json"),
    Route("POST", r"products/reorder", reorder, body="json"),
    Route("GET", r"products/" + ID, get_product),
    Route("PUT", r"products/" + ID, put_product, body="json"),
    Route("DELETE", r"products/" + ID, delete_product),
    Route("POST", r"products/" + ID + r"/duplicate", duplicate_product, body="json"),
]
