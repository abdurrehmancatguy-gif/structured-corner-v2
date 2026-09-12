"""Publish: commit what the admin saved, then send the commits live.

Nothing here runs on a timer, on save or at startup: each step is the owner's
click. publishing.py decides what is included and checked; gitops.py runs
git. The push only ever runs as a background job the UI polls, and never
when the admin was started with --no-push.
"""
import re
import threading

from .. import gitops, jobs, publishing
from ..errors import ApiError
from ..routes import Route

HEX64 = re.compile(r"^[0-9a-f]{64}$")
NO_GIT = "This copy of the shop is not a git checkout, so nothing can be committed or published from here."

# One conversation with GitHub at a time: a second fetch or push waits for
# the owner to try again rather than queueing behind the first.
_NET = threading.Lock()


def _obj(req):
    if not isinstance(req.body, dict):
        raise ApiError(400, "bad_request", "Send a JSON object.")
    return req.body


def _need_git(cfg):
    if not gitops.available(cfg):
        raise ApiError(409, "no_git", NO_GIT)


def get_changes(req):
    return publishing.review(req.app)


def _room_failure(room):
    if room["problems"]:
        return ("Nothing was committed: the site would not build from this commit.",
                room["problems"][:8])
    return ("Nothing was committed: rebuilding this commit changes %d file%s, so both deploys would stop on it. "
            "Rebuild the site (Settings, or any save) and review again." % (len(room["changed"]), "" if len(room["changed"]) == 1 else "s"),
            room["changed"][:12])


def post_commit(req):
    app, cfg = req.app, req.app.cfg
    body = _obj(req)
    message = publishing.check_message(body.get("message"))
    digest = body.get("paths_digest")
    if not isinstance(digest, str) or not HEX64.match(digest):
        raise ApiError(400, "bad_request", "Say which list of changes you reviewed (paths_digest).")
    _need_git(cfg)
    # The store's lock: no save can land between the review and the commit.
    with app.store.transaction("commit"):
        view = publishing.review(app, sentences=False)
        if view["paths_digest"] != digest:
            raise ApiError(409, "changes_moved", "Something changed since you reviewed the list (a save in another "
                           "tab, perhaps). Nothing was committed: review it again.")
        if view["blocking"]:
            raise ApiError(422, "checks_failed", "Nothing was committed: " + view["blocking"][0]["message"],
                           {"checks": view["blocking"]})
        items = publishing.admin_items(view["groups"])
        if not items or not view["head"]:
            raise ApiError(422, "checks_failed", "There is nothing to commit.",
                           {"checks": [{"id": "nothing", "message": "Everything saved is already committed."}]})
        paths = [it["path"] for it in items]
        room = gitops.clean_room(cfg, view["head"], overlay=paths)
        if not room["ok"]:
            msg, rows = _room_failure(room)
            raise ApiError(422, "checks_failed", msg, {"checks": [{"id": "clean_room", "message": msg, "paths": rows}]})
        if gitops.index_locked(cfg):
            raise ApiError(409, "git_locked", "Git is busy in a terminal, so nothing was committed. Try again when "
                           "it has finished.")
        sha = gitops.commit_paths(cfg, message, paths, [it["path"] for it in items if it["untracked"]])
        if not sha:
            raise ApiError(502, "commit_failed", "Git reported no new commit.")
        left = sorted({p for _, p in gitops.status(cfg)} & set(paths))
        subject = message.split("\n", 1)[0]
        publishing.append_log(cfg, {"kind": "commit", "sha": sha, "subject": subject, "files": len(paths),
                                    "actor": app.store.actor})
    return {"sha": sha, "short": sha[:7], "subject": subject, "files": len(paths), "left": left, "check_ms": room["ms"]}


def post_fetch(req):
    cfg = req.app.cfg
    _need_git(cfg)
    if not _NET.acquire(blocking=False):
        raise ApiError(423, "busy", "GitHub is already being checked or published to. Try again in a moment.")
    try:
        remote = gitops.fetch(cfg)
    finally:
        _NET.release()
    publishing.note_fetch(cfg, remote)
    return {"remote_sha": remote, "fetched_at": publishing.fetched_iso(cfg)}


def get_preview(req):
    _need_git(req.app.cfg)
    return publishing.preview(req.app)


def post_push(req):
    app, cfg = req.app, req.app.cfg
    # Before anything else: with --no-push there is no path to git push at all.
    if cfg.no_push:
        raise ApiError(403, "no_push", "This admin was started with --no-push, so it cannot publish. Nothing was "
                       "sent to GitHub.")
    body = _obj(req)
    if body.get("confirm") != "PUBLISH":
        raise ApiError(422, "confirm_required", "Type PUBLISH to confirm.")
    local, remote = body.get("local_sha"), body.get("remote_sha")
    gitops.check_full_sha(local)
    gitops.check_full_sha(remote)
    include = body.get("include_external") is True
    _need_git(cfg)
    publishing.check_preview(app, body.get("preview_id"), local, remote)
    if app.store.busy() or jobs.running("push"):
        raise ApiError(423, "busy", "Something else is running (%s). Try again in a moment."
                       % (app.store.busy() or "a publish"))

    def work(log):
        if not _NET.acquire(blocking=False):
            raise ApiError(423, "busy", "GitHub is already being checked or published to. Try again in a moment.")
        try:
            with app.store.transaction("publish"):
                return publishing.go_live(app, local, remote, include, log)
        finally:
            _NET.release()

    job = jobs.start("push", work)
    return 202, {"job": job.view()}


def get_log(req):
    rows = publishing.read_log(req.app.cfg)
    rows.reverse()
    return {"items": rows[:publishing.LOG_KEEP], "total": len(rows)}


def get_summary(req):
    """The top bar's chip: counts only, from git status and the last fetch.
    Never talks to GitHub."""
    cfg = req.app.cfg
    if not gitops.available(cfg):
        return {"available": False, "saved": 0, "generated": 0, "ahead": None}
    groups = publishing.working_changes(cfg)
    local, remote = gitops.resolve(cfg, "HEAD"), gitops.resolve(cfg, gitops.REMOTE_MAIN)
    ahead = None
    if local and remote and gitops.is_ancestor(cfg, remote, local):
        ahead = len(gitops.commits_between(cfg, remote, local))
    return {"available": True, "saved": len(groups["content"]) + len(groups["media"]),
            "generated": len(groups["generated"]), "ahead": ahead}


ROUTES = [
    Route("GET", r"publish/changes", get_changes),
    Route("GET", r"publish/summary", get_summary),
    Route("POST", r"publish/commit", post_commit, body="json"),
    Route("POST", r"publish/fetch", post_fetch, body="json"),
    Route("GET", r"publish/preview", get_preview),
    Route("POST", r"publish/push", post_push, body="json"),
    Route("GET", r"publish/log", get_log),
]
