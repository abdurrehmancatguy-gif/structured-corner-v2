"""Strict JSON in, canonical JSON out.

Incoming bodies are parsed strictly: a duplicate key could smuggle a second
value past a check that read the first, NaN and Infinity are not JSON, and a
deeply nested body is a way to exhaust the stack.

Content files are written in one canonical form, the one products.json and
the other files already use, so a save shows only the values that changed.
"""
import json

from .errors import ApiError

MAX_DEPTH = 20


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError("duplicate key: %s" % k)
        out[k] = v
    return out


def _no_constants(name):
    raise ValueError("not JSON: %s" % name)


def _depth(obj, d=0):
    if d > MAX_DEPTH:
        raise ValueError("nested deeper than %d" % MAX_DEPTH)
    if isinstance(obj, dict):
        for v in obj.values():
            _depth(v, d + 1)
    elif isinstance(obj, list):
        for v in obj:
            _depth(v, d + 1)


def strict_loads(raw):
    """Parse a request body or raise a 400 the UI can show."""
    try:
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        obj = json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_no_constants)
        _depth(obj)
        return obj
    except (ValueError, UnicodeDecodeError) as e:
        raise ApiError(400, "bad_json", "The request body is not valid JSON.", str(e))


def canonical(obj):
    """The exact bytes a content file is written with."""
    return (json.dumps(obj, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def dumps(obj):
    """Compact JSON for API responses."""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
