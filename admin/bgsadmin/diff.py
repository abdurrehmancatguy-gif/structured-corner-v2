"""What changed between two versions of a product or a document, as short
sentences an owner can read: "Be Mine: price AED 85 to AED 90",
"Banner slide 2: headline changed", "Draft to active: Majlis Ritual Set".

Everything is worded from the schema (labels, choice labels, the kind of each
field), so a field added to a schema module is described without an edit
here. Each difference is a dict:

    {"path": JSON pointer, "where": "Be Mine" or "Banner slide 2" or "",
     "label": "Price", "before": "AED 85", "after": "AED 90", "text": sentence}

before and after are display text for a side-by-side view: "" is an empty
value and "not set" a missing one. Lists of entries (rows) are lined up by
content, so removing the second slide reads as one removal rather than as
every later slide changing.
"""
import difflib
import json
import re

from .service import changed, field_for
from .validate import MISSING, get

SHORT = 40            # text up to this long is quoted in the sentence; longer text just "changed"
CUT = 2000            # longest before/after value sent for the side-by-side view


def _canon(v):
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def _same(a, b):
    if a is MISSING or b is MISSING:
        return a is b
    return _canon(a) == _canon(b)


def _first_lower(s):
    """'Price' reads 'price' after a colon; 'EDP heading' stays as it is."""
    return s[:1].lower() + s[1:] if len(s) > 1 and s[1].islower() else s


def _join(where, what):
    return "%s, %s" % (where, _first_lower(what)) if where else what


def _head(where, label):
    return "%s: %s" % (where, _first_lower(label)) if where else label


def _cut(s):
    return s if len(s) <= CUT else s[:CUT] + "..."


def _unit(f):
    """Money fields, and whole numbers labelled (AED) or (%), are shown with
    their unit and without it in the label."""
    label = f["label"]
    unit = "AED" if f["type"] == "money" else None
    m = re.search(r"\s*\((AED|%)\)$", label)
    if m:
        label, unit = label[:m.start()], m.group(1)
    return label, unit


def _pname(ctx, pid):
    d = (ctx.get("products") or {}).get(pid)
    return (d or {}).get("name") or str(pid)


def _enum_label(f, v):
    for i, x in enumerate(f.get("enum", [])):
        if x == v and type(x) is type(v):
            labels = f.get("enumLabels") or []
            return labels[i] if i < len(labels) else str(v)
    return str(v)


def fmt(f, v, ctx=None):
    """One value as display text."""
    ctx = ctx or {}
    if v is MISSING or v is None:
        return "not set"
    t = f["type"]
    if t in ("int", "money") and isinstance(v, int) and not isinstance(v, bool):
        unit = _unit(f)[1]
        return "AED %d" % v if unit == "AED" else "%d%%" % v if unit == "%" else str(v)
    if t == "bool":
        return "On" if v else "Off"
    if t == "enum":
        return _enum_label(f, v)
    if t == "product-ref":
        return _pname(ctx, v)
    if isinstance(v, list):
        if t == "lines":
            return "\n".join(str(x) for x in v)
        if t == "product-refs":
            return ", ".join(_pname(ctx, x) for x in v) or "none"
        if t == "images":
            return ", ".join(str(x) for x in v) or "none"
        if t == "rows":
            return "\n".join(_title(f, x, i, ctx) for i, x in enumerate(v)) or "none"
    if isinstance(v, (dict, list)):
        return _canon(v)
    return str(v)


def _quote(v):
    if v is MISSING or v is None:
        return "not set"
    return '"%s"' % v if v != "" else "empty"


def _short(v):
    return v is MISSING or v is None or (isinstance(v, str) and len(v) <= SHORT and "\n" not in v)


def _entry(ptr, where, label, before, after, text):
    return {"path": ptr or "/", "where": where, "label": label, "before": _cut(before), "after": _cut(after), "text": text}


def _title(f, item, i, ctx):
    """An entry's name in its list, as the editor shows it: its itemLabel
    field, or its position."""
    key = f.get("itemLabel")
    v = item.get(key) if isinstance(item, dict) and key else None
    if key == "product" and v:
        v = _pname(ctx, v)
    v = str(v or "").replace("\n", " ").strip()
    return v or "Entry %d" % (i + 1)


def item_name(f, n):
    """'Banner slides' and the second entry make 'Banner slide 2'; a label
    that is not a plural makes 'Phone tab bar, entry 2'."""
    words = f["label"].split(" ")
    last = words[-1]
    if len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
        return " ".join(words[:-1] + [last[:-1]]) + " %d" % n
    return "%s, entry %d" % (f["label"], n)


def pointer_label(fields, ptr):
    """A readable name for a JSON pointer: '/hero_slides/2/image' is
    'Banner slide 3: picture'. A pointer no field owns is shown as it is."""
    f, parents = field_for(fields, ptr)
    if f is None and not parents:
        return ptr
    segs = ptr.split("/")[1:]
    where, pos = "", 0
    for g in parents:
        pos += len(g["path"].split("/")) - 1
        idx = segs[pos] if pos < len(segs) else ""
        where = _join(where, item_name(g, int(idx) + 1) if idx.isdigit() else g["label"])
        pos += 1
    return _head(where, _unit(f)[0] if f else "other data")


def _describe(f, item, ctx):
    """An entry added or removed, field by field, for the side-by-side view."""
    lines = []
    for sub in f.get("fields", []):
        v = get(item, sub["path"]) if isinstance(item, dict) else MISSING
        if v is not MISSING and v not in ("", None, []):
            lines.append("%s: %s" % (_unit(sub)[0], fmt(sub, v, ctx).replace("\n", " / ")))
    return "\n".join(lines)


def _sentence(where, f, a, b, ctx):
    head = _head(where, _unit(f)[0])
    t = f["type"]
    if t == "bool" and isinstance(b, bool):
        return "%s turned %s" % (head, "on" if b else "off")
    if t in ("int", "money", "enum", "icon", "tint", "product-ref", "bool"):
        return "%s %s to %s" % (head, fmt(f, a, ctx), fmt(f, b, ctx))
    if t in ("text", "textarea", "href") and _short(a) and _short(b):
        return "%s %s to %s" % (head, _quote(a), _quote(b))
    if t == "images" and isinstance(a, list) and isinstance(b, list):
        if sorted(a) == sorted(b):
            return "%s reordered" % head
        if len(a) != len(b):
            return "%s changed, %d to %d" % (head, len(a), len(b))
    return "%s changed" % head


def _rows(f, a, b, where, ptr, ctx, out):
    la = a if isinstance(a, list) else []
    lb = b if isinstance(b, list) else []
    ca, cb = [_canon(x) for x in la], [_canon(x) for x in lb]
    if len(ca) == len(cb) and sorted(ca) == sorted(cb):
        out.append(_entry(ptr, where, f["label"], fmt(f, la, ctx), fmt(f, lb, ctx), "%s reordered" % _head(where, f["label"])))
        return
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, ca, cb, autojunk=False).get_opcodes():
        if op == "equal":
            continue
        n = min(i2 - i1, j2 - j1) if op == "replace" else 0
        for k in range(n):
            i, j = i1 + k, j1 + k
            name = _join(where, item_name(f, j + 1))
            size = len(out)
            _walk(f.get("fields", []), la[i], lb[j], name, "%s/%d" % (ptr, j), ctx, out)
            if len(out) == size:
                out.append(_entry("%s/%d" % (ptr, j), name, f["label"], _canon(la[i]), _canon(lb[j]), "%s changed" % name))
        for i in range(i1 + n, i2):
            out.append(_entry("%s/%d" % (ptr, i), where, f["label"], _describe(f, la[i], ctx), "",
                              "%s removed (%s)" % (_join(where, item_name(f, i + 1)), _title(f, la[i], i, ctx))))
        for j in range(j1 + n, j2):
            out.append(_entry("%s/%d" % (ptr, j), where, f["label"], "", _describe(f, lb[j], ctx),
                              "%s added (%s)" % (_join(where, item_name(f, j + 1)), _title(f, lb[j], j, ctx))))


def _walk(fields, old, new, where, prefix, ctx, out):
    for f in fields:
        a = get(old, f["path"]) if isinstance(old, dict) else MISSING
        b = get(new, f["path"]) if isinstance(new, dict) else MISSING
        if _same(a, b):
            continue
        ptr = prefix + f["path"]
        if f["type"] == "rows":
            _rows(f, a, b, where, ptr, ctx, out)
            continue
        # A document's own fields are named with their card ("Product films:
        # heading"), since a bare "Heading" could be any of several.
        w = where or f.get("group") or ""
        out.append(_entry(ptr, w, _unit(f)[0], fmt(f, a, ctx), fmt(f, b, ctx), _sentence(w, f, a, b, ctx)))


def _unowned(fields, old, new, where, out):
    """Keys no schema field describes (written by hand, or by an older
    admin), named once each by their top-level key."""
    seen = set()
    for ptr in changed(old, new):
        f, parents = field_for(fields, ptr)
        if f is not None or parents:
            continue
        key = "/" + ptr.split("/")[1]
        if key in seen:
            continue
        seen.add(key)
        a, b = get(old, key), get(new, key)
        out.append(_entry(key, where, key, "not set" if a is MISSING else _canon(a), "not set" if b is MISSING else _canon(b),
                          "%s changed (%s, not edited in the admin)" % (_head(where, "Other data"), key)))


def document(fields, old, new, ctx=None):
    """The differences between two versions of a whole document. None on a
    side means the file did not exist there."""
    if old is None or new is None:
        return [] if old is new else [_entry("/", "", "Document", "not set" if old is None else "", "not set" if new is None else "",
                                              "Created" if old is None else "Removed")]
    out = []
    _walk(fields, old, new, "", "", ctx or {}, out)
    _unowned(fields, old, new, "", out)
    return out


def product(pid, fields, old, new, ctx=None):
    """The differences between two versions of one product. None on a side
    means the product did not exist there."""
    if old is None and new is None:
        return []
    name = (new if isinstance(new, dict) else old).get("name") or pid
    if old is None:
        return [_entry("/", "", "Product", "not set", name, "Added: %s" % name)]
    if new is None:
        return [_entry("/", "", "Product", name, "not set", "Removed: %s" % name)]
    out = []
    was, now = old.get("published", True) is not False, new.get("published", True) is not False
    if was != now:
        out.append(_entry("/published", name, "Status", "Active" if was else "Draft", "Active" if now else "Draft",
                          "%s to %s: %s" % ("Active" if was else "Draft", "active" if now else "draft", name)))
    _walk([f for f in fields if f["path"] != "/published"], old, new, name, "", ctx or {}, out)
    _unowned(fields, old, new, name, out)
    return out


def products(fields, old, new, ctx=None):
    """Every product added, removed or changed between two products.json."""
    old, new = old or {}, new or {}
    out = []
    for pid in list(new) + [p for p in old if p not in new]:
        if _canon(old.get(pid)) != _canon(new.get(pid)):
            out += product(pid, fields, old.get(pid), new.get(pid), ctx)
    return out


def summary(entries, limit=3):
    """One line for a timeline: the first few sentences and how many more."""
    if not entries:
        return "No change"
    more = len(entries) - limit
    return "; ".join(e["text"] for e in entries[:limit]) + ("; and %d more" % more if more > 0 else "")
