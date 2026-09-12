"""Field schemas, one module per resource.

Each module exports RESOURCE ({name, label, kind}) and FIELDS: dicts with
path (a JSON pointer inside the resource; inside rows, inside one item),
type, label and, as needed, help, required, nullable, min, max, maxLength,
itemMaxLength, pattern, patternHelp, enum, enumLabels, multiline, dir, social,
visibleWhen ({"category": [...]}), rendered (False: saved but not shown on the
site yet), locked (the reason, for payments and checkout), readonly (the
reason, for things changed elsewhere), guarded, fields and itemLabel (rows),
canAdd (rows). The UI renders forms from these; the server enforces them.
"""
import ast
import importlib
import pkgutil
import re

_ORDER = ("products", "settings", "copy", "home", "navigation")


def load():
    out = {}
    for m in pkgutil.iter_modules(__path__):
        mod = importlib.import_module("%s.%s" % (__name__, m.name))
        if hasattr(mod, "RESOURCE"):
            out[mod.RESOURCE["name"]] = {"resource": mod.RESOURCE, "fields": mod.FIELDS}
    return {k: out[k] for k in sorted(out, key=lambda k: _ORDER.index(k) if k in _ORDER else 99)}


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
