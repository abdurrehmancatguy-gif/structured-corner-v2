"""Field schemas, one module per resource.

Each module exports RESOURCE ({name, label, kind, intro}) and FIELDS: dicts
with path (a JSON pointer inside the resource; inside rows, inside one item),
type, label and, as needed, help, required, nullable, min, max, maxLength,
itemMaxLength, pattern, patternHelp, enum, enumLabels, multiline, dir, social,
visibleWhen ({"category": [...]}), rendered (False: saved but not shown on the
site yet), locked (the reason, for payments and checkout), readonly (the
reason, for things changed elsewhere), guarded, fields and itemLabel (rows),
canAdd (rows). The UI renders forms from these; the server enforces them.

A module whose kind is "document" is a whole file, flow/content/<name>.json:
adding a document means adding its module and its file, and the store, the
routes and the status poll pick it up from document_names().
"""
import ast
import importlib
import pkgutil
import re

_ORDER = ("products", "settings", "copy", "home", "navigation", "pages", "quiz", "translations")
_LOADED = None


def load():
    """Every module's RESOURCE and FIELDS, products first and the documents in
    the order the admin lists them. Read once per process."""
    global _LOADED
    if _LOADED is None:
        out = {}
        for m in pkgutil.iter_modules(__path__):
            mod = importlib.import_module("%s.%s" % (__name__, m.name))
            if hasattr(mod, "RESOURCE"):
                out[mod.RESOURCE["name"]] = {"resource": mod.RESOURCE, "fields": mod.FIELDS}
        _LOADED = {k: out[k] for k in sorted(out, key=lambda k: (_ORDER.index(k) if k in _ORDER else 99, k))}
    return _LOADED


def document_names():
    """The whole-file documents beside products.json, in the admin's order."""
    return [k for k, v in load().items() if v["resource"]["kind"] == "document"]


def icons(cfg):
    """The icon names build.py can draw (its P table), read without importing
    build.py: importing it would build the site."""
    tree = ast.parse((cfg.flow / "build.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "P" for t in node.targets):
            return sorted(k.value for k in node.value.keys if isinstance(k, ast.Constant))
    return []


def tints(cfg):
    return sorted(set(re.findall(r"\.c-([a-z]+)\b", (cfg.assets / "flow.css").read_text(encoding="utf-8"))))
