"""Products as a spreadsheet: the CSV export, and the import's dry-run plan.

One row per product, in columns that follow Shopify's product CSV where they
map (docs/PLAN.md, CSV). An import never writes on its own: plan() compares
each row with the product as stored and says what would be created, changed,
left as it is or refused, and api/bulk.py applies a plan later, in one
transaction.

A cell a spreadsheet would run as a formula (one starting with = + - @, a
tab or a carriage return) is written with an apostrophe in front, which the
import takes off again. So is a cell that already starts with an apostrophe,
so text that happens to begin with one comes back exactly as it was.

A cell that says what the export would say for the stored product changes
nothing, so exporting and importing the same file is always a no-op, however
the stored value is spelled (a missing key, null or an empty string).
"""
import copy
import csv
import io
import re

from . import validate
from .api.products import DEFAULTS, TEMPLATE
from .errors import ApiError
from .security import safe_join
from .service import refusals

SIZES, IMAGES, STORY = 4, 8, 6
MAX_BYTES = 5 * 1024 * 1024
# Many times the whole catalogue; a file far past it is a mistake, and
# planning it would keep the admin busy for minutes.
MAX_ROWS = 2000
BOM = chr(0xFEFF)
FORMULA = ("=", "+", "-", "@", "\t", "\r")
# The resized copies build.py needs beside every product photo.
DERIVED = ("-card", "-600", "-card-360", "-thumb")

SIZE_HEADS = ["Size %d %s" % (i, part) for i in range(1, SIZES + 1) for part in ("label", "price")]
IMAGE_HEADS = ["Image %d" % i for i in range(1, IMAGES + 1)]
STORY_HEADS = ["Story line %d" % i for i in range(1, STORY + 1)]
HEADERS = (["Handle", "Title", "Status", "Category", "Price", "Default size"] + SIZE_HEADS
           + ["Stock", "Gender", "Top", "Heart", "Base", "Ingredients", "Barcode", "Contents",
              "Never discounted", "Order"]
           + IMAGE_HEADS + ["SEO title", "SEO description", "Image alt", "Name (Arabic)"] + STORY_HEADS)

# Columns that hold one text field each, by the field's key in products.json.
TEXT = {"Title": "name", "Default size": "size", "Top": "top", "Heart": "heart", "Base": "base",
        "Ingredients": "ingredients", "Barcode": "barcode", "Contents": "contents", "SEO title": "seo_title",
        "SEO description": "seo_description", "Image alt": "image_alt", "Name (Arabic)": "name_ar"}
KEYS = dict(TEXT)
KEYS.update({"Status": "published", "Category": "category", "Price": "price", "Stock": "stock",
             "Gender": "gender", "Never discounted": "never_discount", "Order": "order"})
COLUMN_OF = {k: h for h, k in KEYS.items()}


def guard(s):
    return "'" + s if s.startswith(FORMULA + ("'",)) else s


def unguard(s):
    return s[1:] if s.startswith("'") and s[1:].startswith(FORMULA + ("'",)) else s


def column_for(ptr):
    """The column a JSON pointer inside a product is written in, so an error
    can name the cell to fix."""
    parts = (ptr or "").split("/")[1:]
    if not parts:
        return ""
    key = parts[0]
    n = int(parts[1]) + 1 if len(parts) > 1 and parts[1].isdigit() else 1
    if key == "sizes":
        return "Size %d %s" % (n, "price" if parts[2:3] == ["price"] else "label")
    if key == "images":
        return "Image %d" % n
    if key == "story":
        return "Story line %d" % n
    if key == "id":
        return "Handle"
    return COLUMN_OF.get(key, "")


def _text(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    return str(v)


def cells(pid, d):
    """The row the export writes for one product, before the formula guard."""
    c = dict.fromkeys(HEADERS, "")
    c["Handle"] = pid
    for h, k in KEYS.items():
        c[h] = _text(d.get(k))
    c["Status"] = "active" if d.get("published", True) is not False else "draft"
    c["Never discounted"] = "TRUE" if d.get("never_discount") else "FALSE"
    for i, s in enumerate((d.get("sizes") or [])[:SIZES], 1):
        if isinstance(s, dict):
            c["Size %d label" % i], c["Size %d price" % i] = _text(s.get("label")), _text(s.get("price"))
    for i, n in enumerate((d.get("images") or [])[:IMAGES], 1):
        c["Image %d" % i] = _text(n)
    for i, s in enumerate((d.get("story") or [])[:STORY], 1):
        c["Story line %d" % i] = _text(s)
    return c


def export(items):
    """The file for [(id, product)]: UTF-8 with a byte order mark, which is
    how Excel knows to read the Arabic names as UTF-8, and CRLF line ends."""
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(HEADERS)
    for pid, d in items:
        c = cells(pid, d)
        w.writerow([guard(c[h]) for h in HEADERS])
    return (BOM + buf.getvalue()).encode("utf-8")


def read(text):
    """The file's columns (None for one it does not know), its rows as
    [(line, cells or None, problem)] and the column names it ignored.

    A problem with the file as a whole raises 422 bad_csv. A record the csv
    module cannot read (a quote that never closes, say) becomes the last row,
    with its line number: nothing after it can be trusted to line up."""
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError:
        # JSON can carry half of a UTF-16 pair, which is no character at all
        # and could never be written to products.json.
        raise ApiError(422, "bad_csv", "The file has a character in it that is not valid text.")
    if size > MAX_BYTES:
        raise ApiError(413, "too_large", "The file is larger than %d MB." % (MAX_BYTES // (1024 * 1024)))
    if text.startswith(BOM):
        text = text[1:]
    reader = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        header = next(reader, None)
    except csv.Error as e:
        raise ApiError(422, "bad_csv", "The first line could not be read (%s)." % e)
    if not header or not any(h.strip() for h in header):
        raise ApiError(422, "bad_csv", "The file is empty: its first line should name the columns.")
    known = {h.lower(): h for h in HEADERS}
    cols, ignored = [], []
    for name in (h.strip() for h in header):
        col = known.get(name.lower())
        if col and col in cols:
            raise ApiError(422, "bad_csv", "The column %s is in the file twice." % col)
        if name and not col:
            ignored.append(name)
        cols.append(col)
    if "Handle" not in cols:
        raise ApiError(422, "bad_csv", "The first line must name the columns, with Handle (the product id) among them.")
    rows, prev = [], reader.line_num
    while True:
        try:
            got = next(reader)
        except StopIteration:
            break
        except csv.Error as e:
            rows.append((prev + 1, None, "This line could not be read (%s), so nothing after it was read either." % e))
            break
        line, prev = prev + 1, reader.line_num
        if any(x.strip() for x in got):
            rows.append((line, got, None))
        if len(rows) > MAX_ROWS:
            raise ApiError(422, "bad_csv", "The file has more than %d products. Split it into smaller files." % MAX_ROWS)
    return cols, rows, ignored


# ---- turning a row into the product it asks for --------------------------------

STATUS = {"active": True, "draft": False}
BOOLS = {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}


def _e(ptr, code, message):
    return dict(validate.err(ptr, code, message), column=column_for(ptr))


def _either(words):
    return ", ".join(words[:-1]) + " or " + words[-1]


def _int(s):
    m = re.fullmatch(r"\s*([+-]?\d{1,9})(?:\.0*)?\s*", s)
    return int(m.group(1)) if m else None


def _scalars(d, vals, now, creating, errors, warnings):
    """Set each one-value column that says something other than the stored
    product's row (now). On a new product an empty cell keeps the default."""
    for h, key in KEYS.items():
        if h not in vals or vals[h] == now[h]:
            continue
        v, ptr = vals[h], "/" + key
        word = v.strip().lower()
        if creating and not word:
            continue
        if h in TEXT:
            d[key] = v
        elif h == "Status":
            if creating:
                if word != "draft":
                    warnings.append(_e(ptr, "draft", "New products start as drafts: make it active in the product editor when it is ready."))
            elif word in STATUS:
                # another spelling of the stored value (Active) changes nothing
                if STATUS[word] != (d.get(key, True) is not False):
                    d[key] = STATUS[word]
            else:
                errors.append(_e(ptr, "format", "Write active or draft."))
        elif h == "Category":
            if word in validate.CATEGORIES:
                d[key] = word
            else:
                errors.append(_e(ptr, "format", "Write %s." % _either(validate.CATEGORIES)))
        elif h == "Gender":
            gender = {g.lower(): g for g in validate.GENDERS}.get(word)
            if gender:
                d[key] = gender
            elif not word:
                d.pop(key, None)
            else:
                errors.append(_e(ptr, "format", "Write %s." % _either(validate.GENDERS)))
        elif h == "Never discounted":
            if word in BOOLS:
                if BOOLS[word] != bool(d.get(key)):
                    d[key] = BOOLS[word]
            else:
                errors.append(_e(ptr, "format", "Write TRUE or FALSE."))
        elif h == "Order" and creating:
            warnings.append(_e(ptr, "order", "New products go to the end of the list, so the Order cell was not used."))
        elif h == "Order" and not word:
            continue        # an empty cell keeps the position
        elif h == "Stock" and not word:
            d[key] = None   # not tracked
        else:
            n = _int(v)
            if n is None:
                errors.append(_e(ptr, "format", "%s is required." % h if not word else "Write a whole number."))
            else:
                d[key] = n


def _group(vals, now, heads):
    """A group of list columns as the file has them, with the stored
    product's cells for any the file leaves out; None when every one the file
    has matches the stored product."""
    present = [h for h in heads if h in vals]
    if not present or all(vals[h] == now[h] for h in present):
        return None
    return [vals[h] if h in vals else now[h] for h in heads]


def _lists(d, vals, now, errors):
    g = _group(vals, now, SIZE_HEADS)
    if g is not None:
        pairs = [(g[2 * i], g[2 * i + 1]) for i in range(SIZES)]
        while pairs and not (pairs[-1][0].strip() or pairs[-1][1].strip()):
            pairs.pop()
        cur = d.get("sizes") if isinstance(d.get("sizes"), list) else []
        sizes = []
        for i, (label, price) in enumerate(pairs):
            n = _int(price)
            if not label.strip() or n is None:
                errors.append(_e("/sizes/%d/%s" % (i, "price" if label.strip() else "label"), "format",
                                 "Give size %d a label and a whole-number price, or leave both empty." % (i + 1)))
                continue
            item = dict(cur[i]) if i < len(cur) and isinstance(cur[i], dict) else {}
            item.update(label=label, price=n)
            sizes.append(item)
        if pairs:
            d["sizes"] = sizes
        else:
            d.pop("sizes", None)
    g = _group(vals, now, IMAGE_HEADS)
    if g is not None:
        # photos past the last column are kept: the file had no room for them
        names = [x.strip() for x in g if x.strip()] + (d.get("images") or [])[IMAGES:]
        if names or "images" in d:
            d["images"] = names
    g = _group(vals, now, STORY_HEADS)
    if g is not None:
        while g and not g[-1].strip():
            g.pop()
        lines = g + (d.get("story") or [])[STORY:]
        if lines or "story" in d:
            d["story"] = lines


def _unused(d, old, by_key):
    """A value in a column the product's category does not use would be saved
    but never shown, so it is refused rather than kept quietly."""
    out, cat = [], d.get("category")
    for key, v in d.items():
        cats = ((by_key.get(key) or {}).get("visibleWhen") or {}).get("category")
        if cats and cat not in cats and v not in ("", None, []) and v != old.get(key):
            out.append(_e("/" + key, "unused", "%s is not used by %s products: leave this cell empty." % (by_key[key]["label"], cat)))
    return out


def photo_problem(img_dir, name):
    """Why a CSV cannot name this photo, or None. A CSV only names photos the
    shop already has, with the resized copies the build needs."""
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*\.jpg", name) \
            or name[:-4].endswith(DERIVED):
        return "Name one of the shop's photos, such as vibe-1.jpg."
    if safe_join(img_dir, name) is None:
        return "The shop has no photo named %s, and a CSV cannot add one." % name
    if any(safe_join(img_dir, name[:-4] + s + ".jpg") is None for s in DERIVED):
        return "%s has no resized copies yet, so the site could not show it." % name
    return None


def _photos(d, old, img_dir):
    out, had = [], set(old.get("images") or [])
    for i, name in enumerate(d.get("images") or []):
        problem = None if name in had else photo_problem(img_dir, name)
        if problem:
            out.append(_e("/images/%d" % i, "photo", problem))
    return out


def plan(text, products, fields, ctx, img_dir):
    """What importing the file would do, row by row, without writing.

    A row that changes a product goes through the checks a single save does
    (service.enforce, by way of refusals, and validate.product); a new one is
    built from the same template and defaults as POST products, as a draft at
    the end of the list. Returns {rows, planned: {id: (action, product)},
    needs: {id: [guarded fields]}, ignored: [column names], errors: the
    number of error rows}."""
    cols, raw, ignored = read(text)
    by_key = {f["path"].strip("/"): f for f in fields}
    order = max([d.get("order", 0) for d in products.values()] + [0])
    rows, planned, needs, seen = [], {}, {}, {}
    at = cols.index("Handle")
    for line, got, problem in raw:
        row = {"line": line, "id": "", "action": "error", "changes": [], "errors": [], "warnings": []}
        rows.append(row)
        errors, warnings = row["errors"], row["warnings"]
        if problem:
            errors.append(_e("", "unreadable", problem))
            continue
        pid = row["id"] = unguard(got[at]).strip() if at < len(got) else ""
        if len(got) != len(cols):
            errors.append(_e("", "cells", "This line has %d cells, but the first line names %d columns." % (len(got), len(cols))))
            continue
        vals = {c: unguard(v) for c, v in zip(cols, got) if c}
        if not pid:
            errors.append(_e("/id", "required", "Handle is required: it is the product's id, such as royal-amber."))
            continue
        if pid in seen:
            errors.append(_e("/id", "duplicate", "Handle %s is on line %d too." % (pid, seen[pid])))
            continue
        seen[pid] = line
        cur = products.get(pid)
        if cur is None:
            problem = validate.product_id_problem(pid, products)
            if problem:
                errors.append(_e("/id", "id", problem))
                continue
            order += 1
            old = dict(DEFAULTS, published=False, order=order)
            d, now = copy.deepcopy(old), dict.fromkeys(HEADERS, "")
        else:
            old, d, now = cur, copy.deepcopy(cur), cells(pid, cur)
        _scalars(d, vals, now, cur is None, errors, warnings)
        _lists(d, vals, now, errors)
        if cur is None:
            d = {k: d[k] for k in TEMPLATE if k in d}
        row["changes"] = [{"field": h, "before": now[h], "after": v}
                          for h, v in cells(pid, d).items() if h != "Handle" and v != now[h]]
        if cur is not None and d == cur and not errors:
            row["action"] = "unchanged"
            continue
        need, refused = refusals(fields, old, d)
        found, notes = validate.product(pid, d, products, fields, ctx)
        errors += [dict(e, column=column_for(e["path"])) for e in refused + found]
        errors += _unused(d, old, by_key) + _photos(d, old, img_dir)
        warnings += [dict(w, column=column_for(w["path"])) for w in notes]
        if errors:
            continue
        row["action"] = "create" if cur is None else "update"
        planned[pid] = (row["action"], d)
        if need:
            needs[pid] = row["confirm"] = need
    return {"rows": rows, "planned": planned, "needs": needs, "ignored": ignored,
            "errors": sum(r["action"] == "error" for r in rows)}
