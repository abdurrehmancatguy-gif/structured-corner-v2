"""The API's route table, collected from every module in bgsadmin/api/.

Each module exports ROUTES, a list of Route. Nobody edits a central table:
adding an area of the admin means adding a module.
"""
import importlib
import pkgutil
import re

from . import access
from . import api as api_pkg
from . import schema
from .errors import ApiError

# Ids are checked in the pattern itself, so a handler never sees a path
# fragment it did not expect. The document names come from the schema
# modules, so a new document needs no edit here.
ID = r"(?P<id>[a-z0-9]+(?:-[a-z0-9]+)*)"
DOC = r"(?P<name>%s)" % "|".join(re.escape(n) for n in schema.document_names())


class Route:
    """One endpoint. body is None, "json" (parsed before the handler runs,
    capped at `limit` bytes or LIMITS["json"]) or "raw": a file sent as the
    body itself, whose Content-Type must be one of `types` and whose length
    must be at most `limit`. A raw body is not read before the handler runs;
    the handler takes it with req.save_body(path) or req.read_body()."""

    def __init__(self, method, pattern, handler, body=None, limit=None, types=None):
        if body == "raw" and not (limit and types):
            raise ValueError("a raw-body route needs its accepted types and a size limit")
        self.method = method
        self.pattern = pattern
        self.regex = re.compile("^" + pattern + "$")
        self.permission = None          # routes.load() fills this from access.py
        self.handler = handler
        self.body = body
        self.limit = limit
        self.types = frozenset(t.lower() for t in (types or ()))


class Raw:
    """A response that is not JSON, such as a spreadsheet download. It goes
    out with the admin's usual security headers plus the ones given here."""

    def __init__(self, data, ctype, headers=None, status=200):
        self.data = data
        self.ctype = ctype
        self.headers = dict(headers or {})
        self.status = status


def load():
    """Every route, with the permission it needs from access.py. A route with
    no permission there stops the admin starting: a new endpoint cannot be
    served until someone has decided who may call it."""
    out = []
    for m in sorted(pkgutil.iter_modules(api_pkg.__path__), key=lambda m: m.name):
        mod = importlib.import_module("%s.%s" % (api_pkg.__name__, m.name))
        out.extend(getattr(mod, "ROUTES", []))
    missing = []
    for r in out:
        r.permission = access.route_permission(r.method, r.pattern)
        if r.permission is None:
            missing.append("%s %s" % (r.method, r.pattern))
    if missing:
        raise RuntimeError("These endpoints have no permission in access.py: %s" % ", ".join(missing))
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
