"""Warnings that never block a save: site text that states a store rule the
settings no longer hold.

The promises under the banner and the top strip restate the delivery
threshold and fee, the same-day fee and cutoff and cash on delivery in their
own words. build.py prints its own copies of those numbers from settings, but
the text in copy.json is typed by hand, so a rule change leaves it saying the
old number. Each AED amount and time of day is read with the words around it,
and with the other text of the same entry (a promise's detail is read with its
headline), to tell which rule it states.
"""
import re

from .service import field_for
from .validate import cutoff_minutes

AED = re.compile(r"(\+\s?)?AED\s?(\d[\d,]*)")
TIME = re.compile(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s?(AM|PM|am|pm)\b")
TEXT_TYPES = ("text", "textarea", "lines")

# rule key -> how the warning says what the rule is now
SAYS = {
    "free_delivery_over": "free delivery starts over AED %s",
    "delivery_fee": "the delivery fee is AED %s",
    "sameday_fee": "same-day delivery costs AED %s",
    "sameday_cutoff": "the same-day cutoff is %s",
    "cod_max_order": "cash on delivery goes up to AED %s",
    "cod_fee": "the cash on delivery fee is AED %s",
    "gift_threshold": "the free gift starts at AED %s",
}


def _topic(context):
    """Which promise a piece of text is about. Cash on delivery comes first:
    its name has 'delivery' in it."""
    if "cash on delivery" in context or re.search(r"\bcod\b", context):
        return "cod"
    if re.search(r"same[- ]day", context):
        return "sameday"
    if re.search(r"\bgift\b|mystery", context):
        return "gift"
    if re.search(r"deliver|shipping", context):
        return "delivery"
    return None


def _amount_rule(topic, before, after, plus):
    """The rule an AED amount states, from the words just before and after it."""
    if re.search(r"\b(over|above|from|spend)\s*$", before):
        return {"cod": "cod_max_order", "gift": "gift_threshold"}.get(topic, "free_delivery_over")
    if re.search(r"\b(under|up to|below)\s*$", before):
        return "cod_max_order" if topic == "cod" else None
    if re.match(r"\s*below\b", after) and topic in ("delivery", "sameday"):
        return "delivery_fee"
    if plus or re.match(r"\s*fee\b", after):
        return {"cod": "cod_fee", "sameday": "sameday_fee", "delivery": "delivery_fee"}.get(topic)
    return None


def _rules(settings):
    store = settings.get("store") if isinstance(settings, dict) and isinstance(settings.get("store"), dict) else {}
    gift = store.get("gift_with_purchase") if isinstance(store.get("gift_with_purchase"), dict) else {}
    out = {k: store.get(k) for k in ("free_delivery_over", "delivery_fee", "sameday_fee", "cod_max_order", "cod_fee")}
    out["gift_threshold"] = gift.get("threshold")
    out["sameday_cutoff"] = store.get("sameday_cutoff")
    return {k: v for k, v in out.items() if v is not None}


def _strings(obj, ptr=""):
    """Every string in obj with its JSON pointer and the other strings of the
    same entry."""
    if isinstance(obj, dict):
        sibs = [v for v in obj.values() if isinstance(v, str)]
        for k, v in obj.items():
            p = ptr + "/" + str(k).replace("~", "~0").replace("/", "~1")
            if isinstance(v, str):
                yield p, v, sibs
            else:
                yield from _strings(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                yield "%s/%d" % (ptr, i), v, [v]
            else:
                yield from _strings(v, "%s/%d" % (ptr, i))


def _whole(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _where(schema, ptr):
    """'Site text / Promises under the banner, entry 1 / Detail' for /usp/0/sub."""
    f, parents = field_for(schema["fields"], ptr)
    parts, rest = [schema["resource"]["label"]], ptr
    for p in parents:
        idx, _, tail = rest[len(p["path"]) + 1:].partition("/")
        parts.append("%s, entry %d" % (p["label"], int(idx) + 1) if idx.isdigit() else p["label"])
        rest = "/" + tail
    if f:
        parts.append(f["label"])
    return " / ".join(parts)


def stale_rules(copy_data, settings_data, copy_schema):
    """One warning per piece of site text and rule it states wrongly."""
    rules = _rules(settings_data)
    cutoff = cutoff_minutes(rules.get("sameday_cutoff"))
    out, seen = [], set()
    for ptr, text, sibs in _strings(copy_data):
        f, parents = field_for(copy_schema["fields"], ptr)
        if not f or f["type"] not in TEXT_TYPES:
            continue
        unshown = any(g.get("rendered") is False for g in parents + [f])
        topic = _topic(" ".join(sibs).lower())
        found = []
        for m in AED.finditer(text):
            rule = _amount_rule(topic, text[:m.start()].lower(), text[m.end():].lower(), bool(m.group(1)))
            if rule in rules and _whole(rules[rule]) and int(m.group(2).replace(",", "")) != rules[rule]:
                found.append((rule, m.group(0).strip(), "{:,}".format(rules[rule])))
        if topic in ("sameday", "delivery") and cutoff is not None:
            for m in TIME.finditer(text):
                mins = (int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)) * 60 + int(m.group(2) or 0)
                if mins != cutoff:
                    found.append(("sameday_cutoff", m.group(0), rules["sameday_cutoff"]))
        for rule, said, now in found:
            if (ptr, rule) in seen:
                continue
            seen.add((ptr, rule))
            msg = '%s: "%s" says %s, but %s.' % (_where(copy_schema, ptr), text, said, SAYS[rule] % now)
            if unshown:
                msg += " This text is not on the site yet."
            out.append({"path": ptr, "document": "copy", "code": "stale_rule", "rule": rule, "message": msg})
    return out


def after_save(name, data, store, schemas):
    """Warnings for a document just saved: new settings against the site text,
    or new site text against the settings."""
    if "copy" not in schemas:
        return []
    if name == "settings":
        return stale_rules(store.doc("copy")[0], data, schemas["copy"])
    if name == "copy":
        return stale_rules(data, store.doc("settings")[0], schemas["copy"])
    return []
