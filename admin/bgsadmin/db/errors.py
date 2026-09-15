"""How the database's refusals become the API's answers.

The admin's own checks answer first, in their own words (validate.py,
service.py). These are the backstops for anything that gets past them, and
the answers for what only the database can see: another program holding a
lock, or the server gone.

    a named check of migration 001      422 validation, code db_rule, in plain words
    a locked setting                    403 locked_field
    never_discount nobody confirmed     428 guarded_field
    a reference to no product           422 validation, code unknown_product
    removing a product still named      409 referenced
    an id that exists                   409 exists
    NUL or half of a UTF-16 pair        422 validation, code control
    a lock held elsewhere, a deadlock   423 busy (the reel job retries on it)
    the server or connection gone       503 database_unavailable
    anything else                       500: a store bug, with the details in the terminal
"""
import json

import psycopg

from ..errors import ApiError

UNAVAILABLE = ("The database is not answering, so nothing was saved. Start PostgreSQL (brew services start "
               "postgresql@18) and try again; your edit is still on the screen.")
BUSY = ("Another program is using the database. Try again in a moment.",
        {"operation": "another program using the database"})
LOCKED = "Payments, tax, cash on delivery and the other locked settings are changed in code."
BUG = ("The database refused the save for a reason the admin should have caught first. The server's terminal has "
       "the details.")

# The named checks of migration 001: (the field they are about, what the database accepts there).
RULES = {
    "products_id_format": ("", "an id of lower-case words joined by single hyphens, at most 64 characters, not a "
                               "word the browser or the admin reserves"),
    "products_id_fixed": ("", "no change to a product's id"),
    "products_body_object": ("", "a product that is an object"),
    "products_body_sane": ("", "each key once, at most 20 levels deep, and whole numbers only"),
    "products_body_size": ("", "a product of at most 64 KB"),
    "products_text_clean": ("", "text without <, >, a control character other than a line break, a long dash or %%"),
    "products_name_present": ("/name", "a name of 1 to 60 characters"),
    "products_category_known": ("/category", "attars, edp, bakhoor or gift-sets"),
    "products_published_boolean": ("/published", "on or off, always there"),
    "products_never_discount_boolean": ("/never_discount", "on or off, always there"),
    "products_price_whole_1_to_100000": ("/price", "a whole price from 1 to 100000"),
    "products_stock_empty_or_0_to_100000": ("/stock", "nothing, or a whole number from 0 to 100000"),
    "products_order_whole_0_to_100000": ("/order", "a whole number from 0 to 100000"),
    "products_attar_sizes": ("/sizes", "one to four sizes, each labelled once and priced from 1 to 100000, with the "
                                       "product's price one of them"),
    "products_edp_size_and_gender": ("/size", "an EDP with its size and gender"),
    "products_bakhoor_size": ("/size", "bakhoor with its size"),
    "products_gift_set_contents": ("/contents", "a gift set with its contents"),
    "products_not_related_to_itself": ("/related", "related products other than the product itself"),
    "documents_body_object": ("", "a document that is an object"),
    "documents_body_sane": ("", "each key once, at most 20 levels deep, and whole numbers only"),
    "documents_body_size": ("", "a document of at most 1 MB"),
    "documents_text_clean": ("", "text without <, >, a control character other than a line break, a long dash or "
                                 "%%"),
    "documents_kept": ("", "no document removed"),
    "documents_key_fixed": ("", "no change to a document's name"),
}


def unavailable():
    return ApiError(503, "database_unavailable", UNAVAILABLE)


def is_lost(e):
    """Whether e means the server or the connection is gone, or did not
    answer in time."""
    if isinstance(e, psycopg.InterfaceError):
        return True
    s = getattr(e, "sqlstate", None)
    return isinstance(e, psycopg.OperationalError) and (s is None or s[:2] == "08" or s in ("57P01", "57P02", "57P03",
                                                                                          "57014"))


def _paths(detail):
    try:
        return [p["path"] for p in json.loads(detail or "[]") if isinstance(p, dict) and p.get("path")]
    except ValueError:
        return []


def _about(err, where):
    """Name the product a refusal is about, for a bulk save."""
    if where and where[0] == "products" and where[1]:
        err["id"] = where[1]
    return err


def answer(e, deleted=(), dangling=()):
    """The ApiError for a psycopg error a save ran into. deleted: the ids of
    the products the save removed; dangling: the references the database
    found naming no product, as content.dangling() lists them."""
    if is_lost(e):
        return unavailable()
    s = getattr(e, "sqlstate", None) or ""
    diag = getattr(e, "diag", None)
    name = diag.constraint_name if diag is not None else None
    where = getattr(e, "bgs_where", None)       # (resource, product id) the store was writing
    if s in ("55P03", "40P01", "40001"):
        return ApiError(423, "busy", BUSY[0], dict(BUSY[1]))
    if s == "23514" and name in ("documents_locked_values", "locked_values_held"):
        path = (_paths(diag.message_detail) or [""])[0]
        return ApiError(403, "locked_field", LOCKED, {"path": path, "field": path})
    if s == "23514" and name == "products_never_discount_guarded":
        return ApiError(428, "guarded_field", "Confirm the change to Never discounted.",
                        {"path": "/never_discount", "field": "/never_discount"})
    if s == "23503" and name == "product_refs_target":
        still = [r for r in dangling if r[3] in deleted]
        if still:
            return ApiError(409, "referenced", "Take it out of these places first.",
                            {"refs": [{"resource": r[0], "id": None if r[1] == "_" else r[1], "path": r[2]}
                                      for r in still]})
        errs = []
        for res, owner, ptr, target in dangling:
            err = {"path": ptr, "code": "unknown_product", "message": "There is no product with the id %s." % target}
            if res == "products":
                err["id"] = owner
            else:
                err["document"] = res
            errs.append(err)
        return ApiError(422, "validation", "Some fields need attention.", errs or [
            {"path": "", "code": "unknown_product", "message": "A link or reference names a product that does not exist."}])
    if s == "23505" and name == "products_pkey":
        return ApiError(409, "exists", "A product with that id already exists.")
    if s in ("22P05", "22P02", "22021"):
        return ApiError(422, "validation", "Some fields need attention.", [_about(
            {"path": "", "code": "control", "message": "Text may not hold that character."}, where)])
    if s == "23514" and name in RULES:
        path, words = RULES[name]
        return ApiError(422, "validation", "Some fields need attention.", [_about(
            {"path": path, "code": "db_rule", "constraint": name,
             "message": "%s: the database accepts %s" % (path or "The content", words)}, where)])
    return ApiError(500, "internal", BUG)
