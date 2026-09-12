"""The API's route table, collected from every module in bgsadmin/api/.

Each module exports ROUTES, a list of Route. Nobody edits a central table:
adding an area of the admin means adding a module.
"""
import importlib
import pkgutil
import re

from . import api as api_pkg
from .errors import ApiError

# Ids are checked in the pattern itself, so a handler never sees a path
# fragment it did not expect.
ID = r"(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*)"
DOC = r"(?P<name>settings|copy|home|navigation)"


class Route:
    def __init__(self, method, pattern, handler, body=None):
        self.method = method
        self.regex = re.compile("^" + pattern + "$")
        self.handler = handler
        self.body = body          # None, or "json"


def load():
    out = []
    for m in sorted(pkgutil.iter_modules(api_pkg.__path__), key=lambda m: m.name):
        mod = importlib.import_module("%s.%s" % (api_pkg.__name__, m.name))
        out.extend(getattr(mod, "ROUTES", []))
    return out


def match(routes, method, path):
    allowed = set()
    for r in routes:
        m = r.regex.match(path)
        if not m:
            continue
        if r.method == method or (method == "HEAD" and r.method == "GET"):
            return r, m.groupdict()
        allowed.add(r.method)
    if allowed:
        raise ApiError(405, "method", "That action is not allowed here.",
                       headers={"Allow": ", ".join(sorted(allowed))})
    raise ApiError(404, "not_found", "Nothing here.")
