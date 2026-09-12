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
        elif t == "dictionary":
            dictionary(f, v, ptr, errors)
        elif t == "tags":
            tags(f, v, ptr, errors)


TAG = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
TIMES = {1: "once", 2: "twice"}


def tags(f, v, ptr, errors):
    """Short lower-case words, such as the facets a quiz answer looks for.
    A word may appear up to maxRepeat times (once unless the field says
    more): in the quiz a facet listed twice counts twice."""
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        errors.append(err(ptr, "type", "This must be a list of words."))
        return
    if f.get("min") is not None and len(v) < f["min"]:
        errors.append(err(ptr, "too_few", "Pick at least %d." % f["min"]))
    if f.get("max") is not None and len(v) > f["max"]:
        errors.append(err(ptr, "too_many", "Keep this to %d." % f["max"]))
    most = f.get("maxRepeat", 1)
    for i, x in enumerate(v):
        if not TAG.match(x) or len(x) > f.get("itemMaxLength", 40):
            errors.append(err("%s/%d" % (ptr, i), "format",
                              "Use one lower-case word, or words joined by hyphens, like citrus or white-floral."))
        elif v.index(x) == i and v.count(x) > most:
            errors.append(err("%s/%d" % (ptr, i), "repeated",
                              "List %s %s at most." % (x, TIMES.get(most, "%d times" % most))))


def escape(key):
    """A key as one JSON pointer segment."""
    return str(key).replace("~", "~0").replace("/", "~1")


def dictionary(f, v, ptr, errors):
    """Text keys mapped to text values, such as English labels to their Arabic.
    A key must be the exact trimmed text it stands for: the storefront looks
    labels up by it. An empty value is allowed and means not translated yet.
    Each error names its entry (key) and which side it is about (part)."""
    if not isinstance(v, dict):
        errors.append(err(ptr, "type", "This must be a list of texts with their translations."))
        return
    if f.get("max") is not None and len(v) > f["max"]:
        errors.append(err(ptr, "too_many", "Keep this to %d entries." % f["max"]))
    kmax, vmax = f.get("keyMaxLength"), f.get("maxLength")
    for k, val in v.items():
        at = "%s/%s" % (ptr, escape(k))
        p = text_problem(k)
        if not p and not k.strip():
            p = ("required", "Write the text this entry translates.")
        elif not p and k != k.strip():
            p = ("spaces", "Remove the spaces at the start or end: the site matches the text exactly.")
        elif not p and kmax and len(k) > kmax:
            p = ("too_long", "Keep this under %d characters." % kmax)
        if p:
            errors.append(dict(err(at, *p), key=k, part="key"))
        p = text_problem(val) if isinstance(val, str) else ("type", "The translation must be text.")
        if not p and vmax and len(val) > vmax:
            p = ("too_long", "Keep this under %d characters." % vmax)
        if p:
            errors.append(dict(err(at, *p), key=k, part="value"))


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


def document(name, data, fields, ctx):
    errors = []
    if not isinstance(data, dict):
        return [err("", "type", "This document must be a set of fields.")], []
    check(fields, data, "", errors, ctx)
    return errors, []


def product_id_problem(pid, products):
    if not isinstance(pid, str) or not ID.match(pid) or len(pid) > 64:
        return "Use lower-case letters, digits and single hyphens, like royal-amber."
    if pid.replace("-", "") in RESERVED_IDS:
        return "That id is reserved. Pick another."
    if pid in products:
        return "A product with that id already exists."
    return None
