"""Paths, limits and the fixed lists everything else checks against.

Every path the admin touches is derived here from the repository it serves,
so a test can point the whole thing at a temporary clone with --repo. The
documents the admin edits are not listed here: each is a schema module
(schema.document_names()).
"""
import json
import os
import pathlib
import sys

ADMIN = pathlib.Path(__file__).resolve().parent.parent
UI = ADMIN / "ui"

# Request body caps, checked against Content-Length before anything is read.
# A route can set its own (Route(limit=...)); uploads always do.
LIMITS = {
    "json": 2 * 1024 * 1024,
}

# The pages build.py writes (plus 404.html, which it also writes). The
# storefront preview serves these and nothing else at the top level, which is
# what both deploys publish.
PAGES = ("index.html", "collection.html", "product.html", "gift-box.html", "cart.html",
         "checkout.html", "confirmed.html", "track-order.html", "account.html", "quiz.html",
         "corporate.html")

# Files under flow/assets that the deploys leave out: never served locally either.
UNPUBLISHED_ASSETS = {"assets/flow.css", "assets/cat/SOURCES.txt", "assets/fam/SOURCES.txt", "assets/fonts/SOURCES.txt"}


STORES = ("json", "postgres")


class Config:
    """Everything that depends on which checkout is being served. store is
    "json" (flow/content/*.json are the content) or "postgres" (the
    database is, and dsn names it); server.py chooses (choose_store)."""

    def __init__(self, repo, port=4310, storefront_only=False, no_push=False, store="json", dsn=None,
                 host="127.0.0.1", base_url=None):
        self.repo = pathlib.Path(repo).resolve()
        self.flow = self.repo / "flow"
        self.content = self.flow / "content"
        self.backups = self.content / ".backups"
        self.assets = self.flow / "assets"
        self.port = int(port)
        self.storefront_only = bool(storefront_only)
        self.no_push = bool(no_push)
        self.store = store
        self.dsn = dsn
        self.python = sys.executable
        self.host = host
        # Off this machine the admin is reached at its own address, which the
        # Host and Origin checks have to know about as well as the local pair.
        self.base_url = (base_url or "").rstrip("/") or None
        self.hosts = {"localhost:%d" % self.port, "127.0.0.1:%d" % self.port}
        self.origins = {"http://localhost:%d" % self.port, "http://127.0.0.1:%d" % self.port}
        if self.base_url:
            import urllib.parse as _u
            parts = _u.urlsplit(self.base_url)
            self.hosts.add(parts.netloc)
            self.origins.add(parts.scheme + "://" + parts.netloc)
        self.https = bool(self.base_url and self.base_url.startswith("https://"))

    def content_file(self, name):
        return self.content / ("%s.json" % name)

    def generated_files(self):
        """What build.py and make_derivatives.py write: snapshotted by every
        transaction so a failed build can put them back byte for byte."""
        out = [self.flow / p for p in PAGES]
        out += [self.flow / "404.html", self.flow / "robots.txt",
                self.assets / "catalogue.js", self.assets / "flow.min.css", self.assets / "phone.min.css",
                self.flow / "tools" / "derivatives.json"]
        return out


# ---- which store a checkout runs on ------------------------------------------------------
#
# The flags first, then this checkout's own admin/local/store.json (ignored by
# git, so a clone never has one), then the JSON files. No environment variable
# is read: test servers start from clones that inherit the environment, and
# must never reach the owner's database.

def store_file(repo):
    return pathlib.Path(repo).resolve() / "admin" / "local" / "store.json"


def read_store_choice(repo):
    """{"store": ..., "dsn": ...} from admin/local/store.json, or None when
    there is none. ValueError for a file that is not one."""
    p = store_file(repo)
    try:
        raw = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        d = json.loads(raw)
    except ValueError as e:
        raise ValueError("%s is not valid JSON (%s)." % (p, e))
    ok = (isinstance(d, dict) and d.get("store") in STORES and isinstance(d.get("dsn", ""), str)
          and (d["store"] != "postgres" or d.get("dsn")))
    if not ok:
        raise ValueError('%s must hold {"store": "postgres", "dsn": "host=... port=... dbname=... user=..."} or '
                         '{"store": "json"}.' % p)
    return d


def choose_store(repo, store=None, dsn=None):
    """(store, dsn): --store json wins over everything (the way back, even on a
    checkout switched to the database); --store postgres takes --dsn or the
    local file's; --dsn alone means postgres; then the local file; then
    json."""
    if store == "json":
        return "json", None
    if store == "postgres" or dsn:
        if not dsn:
            local = read_store_choice(repo)
            dsn = (local or {}).get("dsn")
            if not dsn:
                raise ValueError("--store postgres needs --dsn, or a DSN in %s." % store_file(repo))
        return "postgres", dsn
    local = read_store_choice(repo)
    if local is None or local["store"] == "json":
        return "json", None
    return "postgres", local["dsn"]


def write_store_choice(repo, store, dsn=None):
    """admin/local/store.json, as dbtool migrate --apply and dbtool use write
    it. A DSN is kept even while the choice is json, so "use postgres" can
    switch back."""
    if store not in STORES:
        raise ValueError("Not a store: %r" % (store,))
    p = store_file(repo)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = {"store": store}
    if dsn:
        data["dsn"] = dsn
    tmp = p.with_name(".store.json.tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(str(tmp), str(p))
    return p
