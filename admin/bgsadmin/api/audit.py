"""The admin's own log, read back: sign-ins, refused sign-ins, sign-outs and
every change to people and roles, newest first, with what is kept and what is
about to go.

Content changes are not here: the store records those with the person's
address on each, and History shows them with the before and after. This is
the log for everything that is not content.

Reading it needs the "audit" permission, which is Admin and Manager. Changing
it is not an endpoint at all: the file is appended to and pruned by the admin
itself, and the only way to keep a copy past the retention period is to
export it, which is why that is here.
"""
from .. import events
from ..routes import Raw, Route

LIMIT = 500


def list_events(req):
    limit = req.query.get("limit")
    try:
        n = max(1, min(LIMIT, int(limit))) if limit else 200
    except ValueError:
        n = 200
    return {"events": events.read(req.app.cfg.repo, limit=n,
                                  kind=req.query.get("kind") or None,
                                  actor=(req.query.get("actor") or "").strip().lower() or None),
            "stats": events.stats(req.app.cfg.repo)}


def export_events(req):
    """The whole log as it stands, for the copy kept before the oldest lines
    reach the retention period."""
    data = events.export(req.app.cfg.repo)
    return Raw(data, "application/x-ndjson",
               {"Content-Disposition": 'attachment; filename="bgs-admin-events.jsonl"'})


ROUTES = [
    Route("GET", r"audit", list_events),
    Route("GET", r"audit/export\.jsonl", export_events),
]
