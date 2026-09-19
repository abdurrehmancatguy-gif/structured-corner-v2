"""Who may do what.

The admin used to have one list of addresses, and being on it meant being
able to do everything. This is that list with a role beside each address, and
a permission on every endpoint, checked on the server before the handler runs.
Hiding a button is not access control: the UI reads the same permissions only
so it does not offer what the server would refuse.

    admin       everything, including managing people and their roles
    manager     everything except managing people and their roles
    marketing   the shop's words, pictures and promotions
    inventory   stock, and nothing else
    accountant  stock, and the orders and sales side when it exists

The named permissions are deliberately small in number and specific in
meaning. Two of them are narrower than an endpoint: "stock" may change a
product's stock and nothing else about it, and "discounts" may change the
discount rules in settings and nothing else in that document. Those are
enforced by comparing what was sent with what is stored, in limits() below,
so a role cannot reach a field by talking to the API directly.

Every route in routes.py must appear in ROUTE_PERMISSIONS. A route that does
not is refused at start-up rather than served without a check.
"""
from .errors import ApiError

# ---- the permissions ---------------------------------------------------------------------

READ = "read"                 # open the admin and see content
CONTENT = "content"           # the shop's words: homepage, pages, navigation, quiz, translations
PRODUCTS = "products"         # add, edit, delete, reorder, import products
STOCK = "stock"               # a product's stock, and nothing else about it
MEDIA = "media"               # upload, attach, trash and restore pictures and films
SETTINGS = "settings"         # store rules, delivery, brand
DISCOUNTS = "discounts"       # the discount rules inside settings, and nothing else there
PUBLISH = "publish"           # commit and push, which is what makes a change live
HISTORY = "history"           # restore an earlier version
STAFF = "staff"               # add people, remove them, change their roles
AUDIT = "audit"               # read the admin's own log of sign-ins and role changes
ORDERS = "orders"             # orders and customers (arrives with the orders work)
ANALYTICS = "analytics"       # the numbers, visible to every role

ALL = (READ, CONTENT, PRODUCTS, STOCK, MEDIA, SETTINGS, DISCOUNTS, PUBLISH, HISTORY, STAFF,
       AUDIT, ORDERS, ANALYTICS)

ROLES = {
    "admin": frozenset(ALL),
    "manager": frozenset(p for p in ALL if p != STAFF),   # can read the log, cannot change who is on it
    "marketing": frozenset((READ, CONTENT, MEDIA, DISCOUNTS, ANALYTICS)),
    "inventory": frozenset((READ, STOCK, ANALYTICS)),
    "accountant": frozenset((READ, STOCK, ORDERS, ANALYTICS)),
}
DEFAULT_ROLE = "admin"        # what a bare address on the list means, as it always did

# What each role is called and what it is for, for the Staff screen and for
# anyone reading the settings file.
ROLE_LABELS = {
    "admin": ("Admin", "Everything, including adding people and setting their roles."),
    "manager": ("Manager", "Everything except people and roles."),
    "marketing": ("Marketing", "The shop's words, pictures and promotions. Cannot change products or prices."),
    "inventory": ("Inventory", "Stock numbers only."),
    "accountant": ("Accountant", "Stock, and the orders and sales side."),
}


def role_ok(role):
    return isinstance(role, str) and role in ROLES


def allows(role, permission):
    return permission in ROLES.get(role, ())


def permissions_of(role):
    return sorted(ROLES.get(role, ()))


# ---- the permission every endpoint needs -------------------------------------------------
#
# Keyed by (method, the route's pattern exactly as routes.py declares it). One
# table, so the whole policy is read in one place rather than hunted through
# eight modules. routes.load() refuses a route that is missing here.

ROUTE_PERMISSIONS = {
    # what anyone signed in may read
    ("GET", r"session"): READ,
    ("GET", r"schema"): READ,
    ("GET", r"status"): READ,
    ("POST", r"status/ack"): READ,
    ("GET", r"jobs/(?P<job>[0-9a-f]{16})"): READ,
    ("GET", r"products"): READ,
    ("GET", r"products/(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*)"): READ,
    ("GET", r"collections"): READ,
    ("GET", r"media"): READ,
    ("GET", r"media/trash"): READ,
    ("GET", r"history"): READ,
    ("GET", r"history/backups"): READ,
    ("GET", r"publish/changes"): READ,
    ("GET", r"publish/summary"): READ,
    ("GET", r"publish/preview"): READ,
    ("GET", r"publish/log"): READ,
    ("GET", r"products/export\.csv"): READ,

    # the shop's words
    ("PUT", r"collections/(?P<key>attars|bakhoor|edp|gift-sets|all)"): CONTENT,
    ("GET", r"collections/(?P<key>attars|bakhoor|edp|gift-sets|all)"): READ,

    # products, and the narrower stock permission (limits() decides which)
    ("POST", r"products"): PRODUCTS,
    ("POST", r"products/reorder"): PRODUCTS,
    ("PUT", r"products/(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*)"): STOCK,
    ("DELETE", r"products/(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*)"): PRODUCTS,
    ("POST", r"products/(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*)/duplicate"): PRODUCTS,
    ("POST", r"products/bulk"): STOCK,
    ("POST", r"products/import"): PRODUCTS,

    # pictures and films
    ("POST", r"media/staging"): MEDIA,
    ("POST", r"media/attach"): MEDIA,
    ("POST", r"media/trash"): MEDIA,
    ("POST", r"media/restore"): MEDIA,

    # the rest of the history screen
    ("GET", r"history/(?P<hid>\d{8}-\d{6}(?:-\d{6})?|[0-9a-f]{7,40})"): READ,
    ("POST", r"history/(?P<hid>\d{8}-\d{6}(?:-\d{6})?|[0-9a-f]{7,40})/restore"): HISTORY,
    ("POST", r"history/prune"): HISTORY,

    # people, roles, and the admin's own log
    ("GET", r"staff"): STAFF,
    ("PUT", r"staff"): STAFF,
    ("GET", r"audit"): AUDIT,
    ("GET", r"audit/export\.jsonl"): AUDIT,

    # going live
    ("POST", r"publish/commit"): PUBLISH,
    ("POST", r"publish/push"): PUBLISH,
    ("POST", r"publish/fetch"): READ,
    ("POST", r"build"): CONTENT,
}


def route_permission(method, pattern, docs=()):
    """The permission a route needs. The document routes are one pattern for
    every document, so which permission they need depends on the document."""
    key = (method, pattern)
    if key in ROUTE_PERMISSIONS:
        return ROUTE_PERMISSIONS[key]
    if pattern.startswith("documents/"):
        return READ if method == "GET" else CONTENT
    return None


# Documents that are not "the shop's words": settings is the store's rules,
# and only SETTINGS (or DISCOUNTS, for the discount fields alone) may write it.
DOCUMENT_PERMISSION = {"settings": SETTINGS}


def document_permission(name, method):
    if method == "GET":
        return READ
    return DOCUMENT_PERMISSION.get(name, CONTENT)


# ---- the two narrower permissions --------------------------------------------------------

# The discount rules: the only part of settings a marketing role may change.
DISCOUNT_PATHS = (
    "/store/volume_tiers", "/store/gift_with_purchase", "/store/gift_box",
    "/store/free_gift_over", "/store/low_stock_at",
)


def _changed_paths(new, old, prefix=""):
    """Every pointer whose value differs between two documents."""
    if isinstance(new, dict) and isinstance(old, dict):
        out = []
        for k in sorted(set(new) | set(old)):
            out += _changed_paths(new.get(k), old.get(k), prefix + "/" + str(k))
        return out
    return [] if new == old else [prefix or "/"]


def check_product_write(role, new, old):
    """A role with STOCK but not PRODUCTS may change a product's stock and
    nothing else, whatever it sends."""
    if allows(role, PRODUCTS) or old is None:
        return
    changed = [p for p in _changed_paths(new, old) if p != "/stock"]
    if changed:
        raise ApiError(403, "not_allowed",
                       "Your role may change stock and nothing else about a product. This save also "
                       "changes: %s." % ", ".join(p.lstrip("/") or "the whole product" for p in changed[:6]),
                       {"role": role, "fields": changed})


def check_settings_write(role, new, old):
    """A role with DISCOUNTS but not SETTINGS may change the discount rules
    and nothing else in settings."""
    if allows(role, SETTINGS):
        return
    if not allows(role, DISCOUNTS):
        raise ApiError(403, "not_allowed", "Your role may not change the store's settings.", {"role": role})
    changed = [p for p in _changed_paths(new, old or {})
               if not any(p == d or p.startswith(d + "/") for d in DISCOUNT_PATHS)]
    if changed:
        raise ApiError(403, "not_allowed",
                       "Your role may change the discount rules and nothing else in settings. This save "
                       "also changes: %s." % ", ".join(p.lstrip("/") for p in changed[:6]),
                       {"role": role, "fields": changed})


# ---- what the server refuses -------------------------------------------------------------

def require(role, permission, what=None):
    """Raise unless the role has the permission. The message says what was
    refused and what the role is, because a person reading it is usually
    someone who has just been told no by a screen they expected to work."""
    if allows(role, permission):
        return
    label = ROLE_LABELS.get(role, (role or "no role",))[0]
    raise ApiError(403, "not_allowed",
                   "%s cannot %s." % (label, what or "do that"),
                   {"role": role, "needs": permission})
