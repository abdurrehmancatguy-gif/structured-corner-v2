"""People and their roles: who may open the admin, and what they may do.

The list lives in admin/local/admin-auth.json, outside git and outside
flow/, beside the Auth0 settings it belongs with. This is the only endpoint
that writes it, and only a role with the "staff" permission reaches it, which
is Admin alone: a Manager may run the shop and may not decide who else can.

Three refusals guard against locking the shop out of its own admin:
the last Admin cannot be removed or demoted, nobody may change their own
role, and nobody may remove themselves. Every change asks for a reason and
is written to the audit trail with it, because a role change is the kind of
thing that is read back months later.
"""
import json

from .. import access, adminauth
from ..errors import ApiError
from ..routes import Route
from ..store.base import actor_now

REASON_MIN = 3


def _me(req):
    return ((req.who or {}).get("email") or "").strip().lower()


def list_staff(req):
    conf = req.app.auth
    if not conf:
        raise ApiError(409, "no_signin", "Sign-in is not set up on this machine, so there is no list of people. "
                                         "admin/local/admin-auth.json is where it lives.")
    return {"people": conf.people(),
            "roles": [{"role": r, "label": access.ROLE_LABELS[r][0], "what": access.ROLE_LABELS[r][1]}
                      for r in sorted(access.ROLES)],
            "me": _me(req)}


def put_staff(req):
    """The whole list at once: [{email, role}], with a reason."""
    conf, cfg = req.app.auth, req.app.cfg
    if not conf:
        raise ApiError(409, "no_signin", "Sign-in is not set up on this machine, so there is no list to change.")
    body = req.body if isinstance(req.body, dict) else {}
    people, reason = body.get("people"), (body.get("reason") or "").strip()
    if len(reason) < REASON_MIN:
        raise ApiError(422, "reason_required",
                       "Say why this changes, in a few words. A role change is read back long after it is made.")
    if not isinstance(people, list) or not people:
        raise ApiError(400, "bad_request", "Send people as a list of {email, role}, and keep at least one Admin.")
    seen = {}
    for item in people:
        if not isinstance(item, dict):
            raise ApiError(400, "bad_request", "Each person is {email, role}.")
        email = (item.get("email") or "").strip().lower()
        role = item.get("role")
        if "@" not in email or email.startswith("@") or email.endswith("@") or " " in email:
            raise ApiError(422, "bad_email", "%s is not an email address." % (email or "(empty)"))
        if not access.role_ok(role):
            raise ApiError(422, "bad_role", "%s is not a role. The roles are: %s."
                           % (role, ", ".join(sorted(access.ROLES))))
        if email in seen:
            raise ApiError(422, "duplicate", "%s is listed twice." % email)
        seen[email] = role

    # yourself first: it is the more useful thing to be told when a change
    # would both demote you and leave nobody in charge
    me, before = _me(req), dict(conf.allowed)
    if me:
        if me not in seen:
            raise ApiError(422, "not_yourself", "You cannot remove yourself. Ask another Admin to do it.")
        if seen[me] != before.get(me):
            raise ApiError(422, "not_yourself", "You cannot change your own role. Ask another Admin to do it.")
    if not any(r == "admin" for r in seen.values()):
        raise ApiError(422, "no_admin", "Keep at least one Admin, or nobody can manage people again.")

    added = sorted(e for e in seen if e not in before)
    removed = sorted(e for e in before if e not in seen)
    changed = sorted("%s %s to %s" % (e, before[e], seen[e]) for e in seen if e in before and before[e] != seen[e])
    if not (added or removed or changed):
        return {"people": conf.people(), "changed": []}

    path = adminauth.path_of(cfg.repo)
    try:
        doc = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as e:
        raise ApiError(500, "unreadable", "%s cannot be read: %s" % (path, e))
    doc["allowed"] = [{"email": e, "role": seen[e]} for e in sorted(seen)]
    adminauth.write_settings(cfg.repo, doc)
    req.app.reload_auth()

    what = "; ".join(filter(None, [
        "added " + ", ".join(added) if added else "",
        "removed " + ", ".join(removed) if removed else "",
        "changed " + ", ".join(changed) if changed else ""]))
    req.app.record("staff", "%s (%s)" % (what, reason), actor=actor_now(req.app.store.actor))
    return {"people": req.app.auth.people(), "changed": added + removed + changed}


ROUTES = [
    Route("GET", r"staff", list_staff),
    Route("PUT", r"staff", put_staff, body="json"),
]
