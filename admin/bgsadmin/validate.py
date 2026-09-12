"""What content may say, checked on the server before anything is written.

Text goes into pages build.py writes and shop.js fills, some of it without
escaping today, so text fields refuse < and > (they would be read as page
code), control characters, the long dash the repo does not use, and '%%' (the
slip that once shipped 'VAT at 5%%'). Links must be pages of this site in the
link grammar below; only the social fields take an outside https address.
Warnings (claim words) are returned but never block a save.
"""
import re

from .config import PAGES

MISSING = object()
PARAMS = {"p", "cat", "q", "tab", "sort", "gender", "price", "ready", "family"}
HREF = re.compile(r"^(?:%s)(?:\?[a-z]+=[a-z0-9,+-]+(?:&[a-z]+=[a-z0-9,+-]+)*)?(?:#[a-z0-9-]+)?$"
                  % "|".join(re.escape(p) for p in PAGES))
SOCIAL = re.compile(r"^https://(?:www\.)?(?:instagram\.com|wa\.me|tiktok\.com)/[A-Za-z0-9._/?=&%@+-]*$")
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RESERVED_IDS = {"constructor", "prototype", "tostring", "valueof", "hasownproperty", "isprototypeof",
                "propertyisenumerable", "tolocalestring", "proto", "admin", "new"}
CLAIMS = ("finest", "purest", "guaranteed", "award", "trusted", "proven", "clinically")
CATEGORIES = ("attars", "edp", "bakhoor", "gift-sets")
GENDERS = ("Him", "Her", "Unisex")


def err(path, code, message):
    return {"path": path, "code": code, "message": message}


def text_problem(s, multiline=False):
    if not isinstance(s, str):
        return "type", "This must be text."
    for ch in s:
        if ch in "<>":
            return "markup", "Leave out < and >: the page would read them as code."
        if ch == "\n" and multiline:
            continue
        if ord(ch) < 32 or ord(ch) == 127:
            return "control", "Remove the invisible character (a line break or tab) from this field."
        if ch in (chr(0x2014), chr(0x2015)):     # the long dashes the repo does not use
            return "em_dash", "Use a hyphen or a colon instead of a long dash."
    if "%%" in s:
        return "percent", "Write a single % sign."
    return None


def href_problem(s, social=False):
    if s == "":
        return None
    if social:
        return None if SOCIAL.match(s) else ("href", "Use a full https link on instagram.com, wa.me or tiktok.com.")
    if not HREF.match(s) or any(p not in PARAMS for p in re.findall(r"[?&]([a-z]+)=", s)):
        return "href", "Link to a page of this shop, such as collection.html?cat=attars or product.html?p=vibe."
    return None


def get(data, path):
    cur = data
    for part in [p for p in path.split("/") if p != ""]:
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return MISSING
    return cur


def check(fields, data, prefix, errors, ctx):
    """Check every schema field present in data; rows recurse into their items."""
    for f in fields:
        v = get(data, f["path"])
        ptr = prefix + f["path"]
        t = f["type"]
        if v is MISSING or (v is None and f.get("nullable")):
            if f.get("required") and v is MISSING:
                errors.append(err(ptr, "required", "%s is required." % f["label"]))
            continue
        if t in ("text", "textarea", "href", "image", "video"):
            if not isinstance(v, str):
                errors.append(err(ptr, "type", "This must be text."))
                continue
            p = text_problem(v, multiline=(t == "textarea" and f.get("multiline", False)))
            if p:
                errors.append(err(ptr, *p))
                continue
            if f.get("required") and not v.strip():
                errors.append(err(ptr, "required", "%s is required." % f["label"]))
            if f.get("maxLength") and len(v) > f["maxLength"]:
                errors.append(err(ptr, "too_long", "Keep this under %d characters." % f["maxLength"]))
            if f.get("pattern") and v and not re.fullmatch(f["pattern"], v):
                errors.append(err(ptr, "format", f.get("patternHelp", "This is not in the expected format.")))
            if t == "href":
                p = href_problem(v, social=f.get("social", False))
                if p:
                    errors.append(err(ptr, *p))
        elif t in ("int", "money"):
            if isinstance(v, bool) or not isinstance(v, int):
                errors.append(err(ptr, "type", "This must be a whole number."))
                continue
            lo = f.get("min", 1 if t == "money" else None)
            if lo is not None and v < lo:
                errors.append(err(ptr, "too_small", "The lowest allowed is %d." % lo))
            if f.get("max") is not None and v > f["max"]:
                errors.append(err(ptr, "too_big", "The highest allowed is %d." % f["max"]))
        elif t == "bool":
            if not isinstance(v, bool):
                errors.append(err(ptr, "type", "This must be on or off."))
        elif t == "enum":
            if v not in f["enum"]:
                errors.append(err(ptr, "choice", "Pick one of the listed options."))
        elif t == "icon":
            if v not in ctx.get("icons", ()):
                errors.append(err(ptr, "choice", "Pick one of the listed icons."))
        elif t == "tint":
            if v not in ctx.get("tints", ()):
                errors.append(err(ptr, "choice", "Pick one of the listed colours."))
        elif t == "lines":
            if not isinstance(v, list):
                errors.append(err(ptr, "type", "This must be a list of lines."))
                continue
            if f.get("max") is not None and len(v) > f["max"]:
                errors.append(err(ptr, "too_many", "Keep this to %d lines." % f["max"]))
            for i, line in enumerate(v):
                p = text_problem(line)
                if p:
                    errors.append(err("%s/%d" % (ptr, i), *p))
                elif f.get("itemMaxLength") and len(line) > f["itemMaxLength"]:
                    errors.append(err("%s/%d" % (ptr, i), "too_long", "Keep each line under %d characters." % f["itemMaxLength"]))
        elif t in ("product-ref", "product-refs"):
            ids = [v] if t == "product-ref" else v
            if not isinstance(ids, list) or not all(isinstance(x, str) for x in ids):
                errors.append(err(ptr, "type", "Pick products from the list."))
                continue
            if f.get("max") is not None and len(ids) > f["max"]:
                errors.append(err(ptr, "too_many", "Pick up to %d." % f["max"]))
            for x in ids:
                if x not in ctx.get("products", {}):
                    errors.append(err(ptr, "unknown_product", "There is no product with the id %s." % x))
        elif t == "images":
            if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                errors.append(err(ptr, "type", "This must be a list of image names."))
        elif t == "rows":
            if not isinstance(v, list):
                errors.append(err(ptr, "type", "This must be a list."))
                continue
            if f.get("min") is not None and len(v) < f["min"]:
                errors.append(err(ptr, "too_few", "Keep at least %d." % f["min"]))
            if f.get("max") is not None and len(v) > f["max"]:
                errors.append(err(ptr, "too_many", "Keep this to %d." % f["max"]))
            for i, item in enumerate(v):
                if not isinstance(item, dict):
                    errors.append(err("%s/%d" % (ptr, i), "type", "Each entry must be a set of fields."))
                    continue
                check(f.get("fields", []), item, "%s/%d" % (ptr, i), errors, ctx)


def claim_warnings(texts, prefix=""):
    out = []
    for ptr, s in texts:
        low = (s or "").lower()
        for w in CLAIMS:
            if re.search(r"\b%s\b" % w, low):
                out.append(err(ptr, "claim", "'%s' is a claim the shop has to be able to back up." % w))
    return out


def product(pid, data, products, fields, ctx):
    """Errors and warnings for one product, on top of the schema checks."""
    errors, warnings = [], []
    if not isinstance(data, dict):
        return [err("", "type", "A product is a set of fields.")], []
    check(fields, data, "", errors, dict(ctx, products=products))
    cat = data.get("category")
    if cat == "attars":
        sizes = data.get("sizes")
        if not isinstance(sizes, list) or not sizes:
            errors.append(err("/sizes", "required", "An attar needs at least one size with its price."))
        else:
            labels = [s.get("label") for s in sizes if isinstance(s, dict)]
            if len(labels) != len(set(labels)):
                errors.append(err("/sizes", "duplicate", "Two sizes have the same label."))
            if data.get("price") not in [s.get("price") for s in sizes if isinstance(s, dict)]:
                errors.append(err("/price", "default_size", "The price must be one of the sizes' prices: it is the size the card shows first."))
    elif cat == "edp":
        for k, label in (("size", "Size"), ("gender", "Worn by")):
            if not data.get(k):
                errors.append(err("/" + k, "required", "%s is required for an EDP spray." % label))
    elif cat == "bakhoor":
        if not data.get("size"):
            errors.append(err("/size", "required", "Weight is required for bakhoor."))
    elif cat == "gift-sets":
        if not data.get("contents"):
            errors.append(err("/contents", "required", "Say what is in the set."))
    rel = data.get("related") or []
    if pid in rel:
        errors.append(err("/related", "self", "A product cannot be related to itself."))
    texts = [("/name", data.get("name", ""))] + [("/story/%d" % i, s) for i, s in enumerate(data.get("story") or []) if isinstance(s, str)]
    warnings += claim_warnings(texts)
    return errors, warnings


def cutoff_minutes(text):
    """'2:00 PM' as minutes after midnight, or None when it does not read as a time."""
    m = re.fullmatch(r"(1[0-2]|[1-9]):([0-5]\d) (AM|PM)", text) if isinstance(text, str) else None
    if not m:
        return None
    return (int(m.group(1)) % 12 + (12 if m.group(3) == "PM" else 0)) * 60 + int(m.group(2))


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def settings_rules(data):
    """What one field cannot say alone: the same-day cutoff has to fall in
    shop hours, and the volume ladder has to climb. A rung that needs more
    items but saves the same or less would tell the bag 'add 3 more to save
    5%' while it already saves 10%."""
    errors = []
    store = data.get("store") if isinstance(data.get("store"), dict) else {}
    mins = cutoff_minutes(store.get("sameday_cutoff"))
    if mins is not None and not 6 * 60 <= mins <= 22 * 60:
        errors.append(err("/store/sameday_cutoff", "range", "Pick a time between 6:00 AM and 10:00 PM."))
    rungs = store.get("volume_ladder")
    for i in range(1, len(rungs) if isinstance(rungs, list) else 0):
        a, b = rungs[i - 1], rungs[i]
        if not isinstance(a, dict) or not isinstance(b, dict):
            continue
        ptr = "/store/volume_ladder/%d" % i
        if _whole(a.get("units")) and _whole(b.get("units")) and b["units"] <= a["units"]:
            errors.append(err(ptr + "/units", "order", "Each rung needs more items than the rung before it."))
        if _whole(a.get("percent")) and _whole(b.get("percent")) and b["percent"] <= a["percent"]:
            errors.append(err(ptr + "/percent", "order", "Each rung has to save more than the rung before it."))
    return errors


# Document-level checks, run after the field checks: name -> fn(data) -> errors.
DOCUMENT_CHECKS = {"settings": settings_rules}


def document(name, data, fields, ctx):
    errors = []
    if not isinstance(data, dict):
        return [err("", "type", "This document must be a set of fields.")], []
    check(fields, data, "", errors, ctx)
    if name in DOCUMENT_CHECKS:
        errors += DOCUMENT_CHECKS[name](data)
    return errors, []


def product_id_problem(pid, products):
    if not isinstance(pid, str) or not ID.match(pid) or len(pid) > 64:
        return "Use lower-case letters, digits and single hyphens, like royal-amber."
    if pid.replace("-", "") in RESERVED_IDS:
        return "That id is reserved. Pick another."
    if pid in products:
        return "A product with that id already exists."
    return None
