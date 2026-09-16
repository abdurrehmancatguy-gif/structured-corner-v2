"""What a commit and a publish would carry, and the checks in front of them.

The admin commits only what it owns: content (flow/content/*.json), media
(photos and films under flow/assets/img, cat and video) and the files build.py
and make_derivatives.py generate from them. Build-affecting code and
everything else in the working tree is listed as not included and never
staged. Going live pushes commits that are already made; see docs/PLAN.md,
publish_flow, for the whole flow.
"""
import datetime
import hashlib
import hmac
import json
import os
import re
import threading
import time

from . import diff, gitops, lint
from . import schema as schema_mod
from .config import PAGES, UNPUBLISHED_ASSETS
from .errors import ApiError
from .service import field_for

GROUPS = ("content", "media", "generated", "code", "other")
ADMIN_GROUPS = ("content", "media", "generated")
CODE = {"flow/build.py", "flow/assets/shop.js", "flow/assets/flow.css", "flow/edp_data.json"}
# the phone design's stylesheets, which build.py joins into assets/phone.min.css
PHONE_CSS = re.compile(r"^flow/phone/[a-z0-9_-]+\.css$")
GENERATED = ({"flow/" + p for p in PAGES}
             | {"flow/404.html", "flow/robots.txt", "flow/favicon.ico", "flow/assets/catalogue.js",
                "flow/assets/flow.min.css", "flow/assets/phone.min.css", "flow/tools/derivatives.json"}
             # make_favicon.py writes these beside the photos, from the emblem,
             # so they are listed with what the tools make, not as new photos
             | {"flow/assets/img/favicon-32.png", "flow/assets/img/favicon-16.png",
                "flow/assets/img/apple-touch-icon.png"})
CONTENT = re.compile(r"^flow/content/[a-z0-9_-]+\.json$")
MEDIA = re.compile(r"^flow/assets/(?:img|cat|video)/(?:[^/]+/)*[^/]+\.(?:jpg|jpeg|png|mp4)$")
MEDIA_KIND = {"jpg": "image", "jpeg": "image", "png": "image", "mp4": "video"}
LOG_KEEP = 200
PREVIEW_TTL = 600

_LOG_LOCK = threading.Lock()
_FETCHED = {}          # repo path -> {"remote_sha", "at"} of this run's last fetch


def group_of(path):
    """Which of the five groups a repo-relative path belongs to."""
    if path in CODE or PHONE_CSS.match(path):
        return "code"
    if path in GENERATED:
        return "generated"
    if CONTENT.match(path):
        return "content"
    if MEDIA.match(path):
        return "media"
    return "other"


def _change(xy):
    if xy == "??" or "A" in xy:
        return "added"
    if "D" in xy:
        return "deleted"
    return "modified"


def working_changes(cfg):
    """The working tree against HEAD, partitioned: {group: [{path, change,
    untracked, bytes}]}, each list sorted by path."""
    groups = {g: [] for g in GROUPS}
    for xy, path in sorted(set(gitops.status(cfg)), key=lambda r: r[1]):
        item = {"path": path, "change": _change(xy), "untracked": xy == "??"}
        if item["change"] != "deleted":
            try:
                item["bytes"] = (cfg.repo / path).stat().st_size
            except OSError:
                item["change"] = "deleted"
        if group_of(path) == "media":
            item["kind"] = MEDIA_KIND.get(path.rsplit(".", 1)[-1].lower(), "file")
        groups[group_of(path)].append(item)
    return groups


def admin_items(groups):
    return [it for g in ADMIN_GROUPS for it in groups[g]]


def paths_digest(cfg, items):
    """sha256 of the (path, blob sha) list the owner reviewed: a save in
    another tab, or any edit to one of these files, changes it."""
    rows = sorted([it["path"], gitops.blob_sha(cfg.repo / it["path"]) or "deleted"] for it in items)
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


# ---- sentences --------------------------------------------------------------------

def _json(raw):
    if raw is None:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return ValueError


def describe(paths, read_old, read_new):
    """What customers will see differently, per changed content file:
    [{file, name, label, entries}], each entry as diff.py makes it plus
    `guarded` for a field that asks first (never discounted) and `pid` for a
    product. read_old and read_new give a file's bytes, or None."""
    S = schema_mod.load()
    loaded = {rel: (_json(read_old(rel)), _json(read_new(rel))) for rel in paths}
    prod = loaded.get("flow/content/products.json")
    ctx = {"products": (prod[1] if prod and isinstance(prod[1], dict) else None) or {}}
    out = []
    for rel in paths:
        name = rel[len("flow/content/"):-len(".json")]
        old, new = loaded[rel]
        label = S[name]["resource"]["label"] if name in S else name + ".json"
        if ValueError in (old, new):
            entries = [{"path": "/", "where": "", "label": label, "before": "", "after": "",
                        "text": "%s: the file is not valid JSON" % label}]
        elif name == "products":
            fields = S["products"]["fields"]
            entries = []
            old, new = old or {}, new or {}
            for pid in list(new) + [p for p in old if p not in new]:
                if json.dumps(old.get(pid), sort_keys=True) != json.dumps(new.get(pid), sort_keys=True):
                    for e in diff.product(pid, fields, old.get(pid), new.get(pid), ctx):
                        entries.append(dict(e, pid=pid))
        elif name in S:
            fields = S[name]["fields"]
            entries = diff.document(fields, old, new, ctx)
        else:
            fields = []
            entries = [{"path": "/", "where": "", "label": label, "before": "", "after": "",
                        "text": "%s changed (not edited in the admin)" % label}]
        for e in entries:
            f, parents = field_for(fields, e.get("path", "")) if fields else (None, [])
            e["guarded"] = any(g.get("guarded") for g in parents + ([f] if f else []))
        if entries:
            out.append({"file": rel, "name": name, "label": label, "entries": entries})
    return out


def _names(items):
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def suggest(described, media, generated):
    """A subject in the repo's style, from what actually changed:
    'Change the price of Be Mine to AED 90', 'Update Be Mine and the
    homepage, add 2 photos'. The owner can edit it before committing."""
    parts = []
    entries = [e for d in described for e in d["entries"]]
    if len(entries) == 1:
        e = entries[0]
        name = e.get("where") or ""
        if e.get("text", "").startswith("Added: "):
            parts.append("add " + e["text"][len("Added: "):])
        elif e.get("text", "").startswith("Removed: "):
            parts.append("remove " + e["text"][len("Removed: "):])
        elif e.get("path") == "/published":
            parts.append("make %s %s" % (name, "a draft" if e.get("after") == "Draft" else "active"))
        elif e.get("after") not in (None, "", "not set") and len(str(e["after"])) <= 30 and e.get("label"):
            what = e["label"][:1].lower() + e["label"][1:]
            parts.append("change the %s%s to %s" % (what, " of " + name if name else "", e["after"]))
    if not parts and described:
        things = []
        for d in described:
            if d["name"] == "products":
                names = []
                for e in d["entries"]:
                    n = e.get("where") or (e.get("after") if e.get("after") not in ("", "not set") else e.get("before"))
                    if n and n not in names:
                        names.append(n)
                things += names if len(names) <= 2 else ["%d products" % len(names)]
            else:
                things.append("the " + d["label"][:1].lower() + d["label"][1:])
        parts.append("update " + _names(things) if things else "update the content")
    added = [m for m in media if m["change"] == "added"]
    others = [m for m in media if m["change"] != "added"]
    for group, verb in ((added, "add"), (others, "replace")):
        if group:
            kinds = {m.get("kind") for m in group}
            noun = "photo" if kinds == {"image"} else "film" if kinds == {"video"} else "file"
            if verb == "replace" and all(m["change"] == "deleted" for m in group):
                verb = "remove"
            parts.append("%s %s" % (verb, ("a " + noun) if len(group) == 1 else "%d %ss" % (len(group), noun)))
    if not parts:
        parts.append("rebuild the pages" if generated else "update the content")
    subject = ", ".join(parts)
    if len(subject) > 72:
        n = sum(len(d["entries"]) for d in described)
        subject = "update the content in %d places" % n if n else "update the content"
    return subject[:1].upper() + subject[1:]


# ---- the commit message --------------------------------------------------------------

TRAILER = re.compile(r"^[A-Za-z][A-Za-z-]*-by\s*:", re.I | re.M)
ATTRIBUTION = re.compile(r"generated (?:with|by)|co-authored", re.I)


def check_message(msg):
    """The repo's commit style: a subject of at most 72 characters, no long
    dash, no trailer or attribution line of any kind. Returns the message
    tidied, with one blank line between the subject and any body."""
    if not isinstance(msg, str) or not msg.strip():
        raise ApiError(422, "validation", "Write a commit message.",
                       [{"path": "/message", "code": "required", "message": "Write a commit message."}])
    msg = msg.replace("\r\n", "\n").strip()
    lines = msg.split("\n")
    subject = lines[0].strip()
    body = "\n".join(line.rstrip() for line in lines[1:]).strip()
    problems = []
    if len(subject) > 72:
        problems.append("Keep the first line to 72 characters (it has %d)." % len(subject))
    if not re.match(r"[A-Za-z0-9]", subject):
        problems.append("Start the message with a word.")
    if any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in msg):
        problems.append("Remove the invisible characters, such as tabs.")
    if chr(0x2014) in msg or chr(0x2015) in msg:
        problems.append("Use a hyphen or a colon instead of a long dash.")
    if TRAILER.search(msg) or ATTRIBUTION.search(msg) or chr(0x1F916) in msg:
        problems.append("Leave out trailer and attribution lines, such as Co-Authored-By or Signed-off-by.")
    if len(msg) > 4000:
        problems.append("Keep the message under 4000 characters.")
    if problems:
        raise ApiError(422, "validation", problems[0],
                       [{"path": "/message", "code": "message", "message": p} for p in problems])
    return subject + ("\n\n" + body if body else "")


# ---- the publish log -------------------------------------------------------------------

def _log_file(cfg):
    return cfg.backups / "publish-log.jsonl"


def append_log(cfg, entry):
    """One line per commit or publish made here. It is how a commit is known
    to be made in the admin, so it is only ever appended to."""
    entry = dict(entry, at=datetime.datetime.now().astimezone().isoformat(timespec="seconds"))
    cfg.backups.mkdir(parents=True, exist_ok=True)
    with _LOG_LOCK:
        with open(str(_log_file(cfg)), "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_log(cfg):
    """Every entry, oldest first. A line that does not parse is skipped."""
    out = []
    try:
        with open(str(_log_file(cfg)), encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict):
                    out.append(row)
    except FileNotFoundError:
        pass
    return out


def admin_shas(cfg):
    return {r["sha"] for r in read_log(cfg) if r.get("kind") == "commit" and isinstance(r.get("sha"), str)}


def note_fetch(cfg, remote):
    _FETCHED[str(cfg.repo)] = {"remote_sha": remote, "at": time.time()}


def last_fetch(cfg):
    return _FETCHED.get(str(cfg.repo))


# ---- Not committed -------------------------------------------------------------------

def blockers(app, groups):
    """Why a commit cannot be made now: [{id, message}], empty when it can."""
    cfg = app.cfg
    out = []
    b = gitops.branch(cfg)
    if b != "main":
        out.append({"id": "branch", "message": "The repository is on %s, not main. A developer must switch back to "
                    "main from Terminal." % ("the branch " + b if b else "a single commit instead of a branch")})
    op = gitops.in_progress(cfg)
    if op:
        out.append({"id": "operation", "message": "Git is in the middle of %s. A developer must finish it from "
                    "Terminal first." % op})
    if gitops.index_locked(cfg):
        out.append({"id": "index_lock", "message": "Git is busy in a terminal (it holds the index lock). Try again "
                    "when it has finished."})
    if groups["code"]:
        out.append({"id": "code", "message": "A developer has uncommitted code changes; commit those first.",
                    "detail": "The pages carry version tokens of shop.js and flow.css, so committing them without "
                    "that code would make the deploys' own rebuild differ, and both deploys would fail.",
                    "paths": [it["path"] for it in groups["code"]]})
    if app.build.get("ok") is False:
        out.append({"id": "build", "message": "The last build failed. Fix what it reported and save again before "
                    "committing.", "problems": app.build.get("problems") or []})
    # Checkout and the order-confirmed page state the delivery rules in text a
    # developer sets in code (lint.LOCKED_PAGES). If a settings change has left
    # that text saying something the rest of the site no longer does, a commit
    # would put contradictory delivery promises live, so it is blocked until a
    # developer updates those pages or the settings go back.
    try:
        mism = lint.locked_pages(app.store.doc("settings")[0])
    except Exception:
        mism = []
    if mism:
        pages = " and ".join(w["message"].split(" is locked")[0] for w in mism)
        out.append({"id": "locked_pages", "message": "%s state delivery rules that a developer sets in code, and the "
                    "current settings no longer match them. A developer must update those pages, or the settings "
                    "must go back, before this can go live." % pages,
                    "detail": " ".join(w["message"] for w in mism)})
    return out


def _read(cfg, rel):
    try:
        return (cfg.repo / rel).read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None


def review(app, sentences=True):
    """Publish > Not committed: what GET publish/changes returns."""
    cfg = app.cfg
    if not gitops.available(cfg):
        return {"available": False, "branch": None, "head": None, "groups": {g: [] for g in GROUPS}, "described": [],
                "blocking": [{"id": "git", "message": "This copy of the shop is not a git checkout, so nothing can "
                              "be committed from here."}],
                "warnings": [], "paths_digest": None, "suggested_message": "", "can_commit": False,
                "counts": {"saved": 0, "generated": 0, "not_included": 0}}
    head = gitops.resolve(cfg, "HEAD")
    groups = working_changes(cfg)
    items = admin_items(groups)
    described = []
    if sentences and groups["content"]:
        described = describe([it["path"] for it in groups["content"]],
                             lambda rel: gitops.show_file(cfg, head, rel) if head else None,
                             lambda rel: _read(cfg, rel))
    block = blockers(app, groups)
    warnings = []
    ext = app.store.external_changes()
    if ext:
        warnings.append({"id": "external", "message": "Changed outside the admin: %s. The commit check rebuilds the "
                         "site from these files, so pages that were not rebuilt are caught before anything is "
                         "committed." % ", ".join(ext)})
    return {"available": True, "branch": gitops.branch(cfg), "head": head, "groups": groups, "described": described,
            "blocking": block, "warnings": warnings, "paths_digest": paths_digest(cfg, items),
            "suggested_message": suggest(described, groups["media"], groups["generated"]) if items else "",
            "can_commit": bool(items) and not block and head is not None,
            "counts": {"saved": len(groups["content"]) + len(groups["media"]), "generated": len(groups["generated"]),
                       "not_included": len(groups["code"]) + len(groups["other"])}}


# ---- Not live ---------------------------------------------------------------------------

TEXT_TYPES = (".html", ".js", ".css", ".txt", ".json", ".xml", ".svg", ".webmanifest")
ASSET_TYPES = (".jpg", ".png", ".mp4", ".js", ".css", ".ico", ".txt", ".woff2")
DASH_SWEEP = re.compile(r"^(?:[^/]+\.html|assets/[^/]+\.js|assets/flow\.min\.css)$")
LOCAL_REFS = (b"/admin", b"localhost", b":4310")
MAX_BYTES = 25 * 1024 * 1024
SECRETS = (("a private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
           ("an AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
           ("a GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{30,}|\bgithub_pat_[A-Za-z0-9_]{20,}")),
           ("a Stripe live key", re.compile(r"\b[sr]k_live_[0-9A-Za-z]{16,}")),
           ("a Slack token", re.compile(r"\bxox[abprs]-[0-9A-Za-z-]{10,}")))
ENV_FILE = re.compile(r"(?:^|/)\.env(?:\.[^/]*)?$")
KINDS = ("pages", "images", "video", "code", "other")
CHANGE = {"A": "added", "D": "deleted", "M": "modified"}
PUBLISHED_CHECKS = (("dash", "No long dash in the pages and scripts"),
                    ("local_ref", "No address of this admin (/admin, localhost, :4310) in published files"),
                    ("admin_folder", "No flow/admin folder"),
                    ("types", "Only photos, films, scripts, styles, icons and text under assets"),
                    ("size", "No published file over 25 MB"))
_ROOMS = {}            # (repo, sha) -> clean-room result: a commit never changes


def published(path):
    """Whether a repo-relative path is in what both deploys publish:
    flow/*.html, favicon.ico, robots.txt and flow/assets less two files."""
    if not path.startswith("flow/"):
        return False
    rel = path[5:]
    if "/" not in rel:
        return rel.endswith(".html") or rel in ("favicon.ico", "robots.txt")
    return rel.startswith("assets/") and rel not in UNPUBLISHED_ASSETS


def _kind_of(path):
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    if ext == "html":
        return "pages"
    if ext in ("jpg", "jpeg", "png", "ico", "webp", "gif"):
        return "images"
    if ext == "mp4":
        return "video"
    if ext in ("js", "css"):
        return "code"
    return "other"


def _riding(path):
    if path.startswith("admin/"):
        return "Admin code"
    if path.startswith("flow/tools/"):
        return "Tools"
    if path in CODE or PHONE_CSS.match(path):
        return "Site code (the published copy is rebuilt from it)"
    if path.lower().endswith(".md"):
        return "Notes and documents"
    if path.startswith(".github/") or path in ("netlify.toml", "_redirects", ".gitignore"):
        return "Deploy settings"
    return "Other"


def inspect_published(flow):
    """The published-file checks, run on the exported commit before its
    rebuild: no long dash in the pages and scripts (the repo's own sweep), no
    address of this admin, only the allowed types under assets/, no admin
    folder, no file over 25 MB."""
    found = []
    root = str(flow)
    if (flow / "admin").exists():
        found.append({"id": "admin_folder", "path": "flow/admin", "message": "flow/admin exists, and flow/ is what gets published."})
    for d, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root).replace(os.sep, "/")
            if not published("flow/" + rel):
                continue
            if os.path.getsize(p) > MAX_BYTES:
                found.append({"id": "size", "path": "flow/" + rel, "message": "flow/%s is over 25 MB." % rel})
            if rel.startswith("assets/") and not rel.lower().endswith(ASSET_TYPES):
                found.append({"id": "types", "path": "flow/" + rel, "message": "flow/%s is not a type the site publishes." % rel})
            if rel.lower().endswith(TEXT_TYPES):
                with open(p, "rb") as fh:
                    data = fh.read()
                if DASH_SWEEP.match(rel) and chr(0x2014).encode("utf-8") in data:
                    found.append({"id": "dash", "path": "flow/" + rel, "message": "flow/%s has a long dash." % rel})
                hit = next((s for s in LOCAL_REFS if s in data), None)
                if hit:
                    found.append({"id": "local_ref", "path": "flow/" + rel,
                                  "message": "flow/%s mentions %s." % (rel, hit.decode("ascii"))})
    return found


def scan_secrets(cfg, remote, local, names):
    """Private keys and tokens in the lines the push would add, and .env files."""
    found, seen = [], set()
    for s, p in names:
        if s != "D" and ENV_FILE.search(p):
            found.append({"id": "env_file", "path": p, "message": "%s looks like an environment file, which holds secrets." % p})
    path = None
    for line in gitops.diff_text(cfg, remote, local).split("\n"):
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else line[4:]
            continue
        if not line.startswith("+"):
            continue
        for what, rx in SECRETS:
            if (path, what) not in seen and rx.search(line):
                seen.add((path, what))
                found.append({"id": "secret", "path": path, "message": "%s may contain %s." % (path, what)})
    return found


def room_for(cfg, sha):
    """The clean room of one commit, remembered by sha. A build that could not
    finish (a timeout, say) is not remembered, so the next check runs it again."""
    key = (str(cfg.repo), sha)
    hit = _ROOMS.get(key)
    if hit is None:
        hit = gitops.clean_room(cfg, sha, inspect=inspect_published)
        if hit["ok"] or hit["changed"]:
            if len(_ROOMS) > 50:
                _ROOMS.clear()
            _ROOMS[key] = hit
    return hit


def _files_digest(pub, commits):
    rows = [[c["sha"] for c in commits], [[s, p] for s, p in pub]]
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def preview_id(token, local, remote, digest, issued=None):
    """HMAC of what the owner reviewed, keyed with this run's token and
    stamped, so a publish can only follow a review made here in the last ten
    minutes of exactly these commits and files."""
    issued = int(time.time() if issued is None else issued)
    msg = ("%s|%s|%s|%d" % (local, remote, digest, issued)).encode("utf-8")
    return "%d.%s" % (issued, hmac.new(token.encode("utf-8"), msg, hashlib.sha256).hexdigest())


def _iso(ts):
    return datetime.datetime.fromtimestamp(ts).astimezone().isoformat(timespec="seconds")


def fetched_iso(cfg):
    f = last_fetch(cfg)
    return _iso(f["at"]) if f else None


def preview(app):
    """Publish > Not live: what GET publish/preview returns. Each check says
    why it failed; a preview_id is issued only when every one passes."""
    cfg = app.cfg
    fetched = last_fetch(cfg)
    local, remote = gitops.resolve(cfg, "HEAD"), gitops.resolve(cfg, gitops.REMOTE_MAIN)
    checks = []

    def check(cid, label, ok, detail=""):
        checks.append({"id": cid, "label": label, "ok": bool(ok), "detail": "" if ok else detail})

    b, op = gitops.branch(cfg), gitops.in_progress(cfg)
    check("branch", "On the main branch, with nothing half-done in git", b == "main" and not op,
          ("Git is in the middle of %s." % op) if op else
          "The repository is on %s, not main." % ("the branch " + b if b else "a single commit"))
    check("fetched", "GitHub checked since the admin started", fetched is not None and remote is not None,
          "Check GitHub first." if fetched is None else "This computer does not know GitHub's main branch.")
    ancestor = bool(local and remote and gitops.is_ancestor(cfg, remote, local))
    behind = len(gitops.commits_between(cfg, local, remote)) if local and remote and not ancestor else 0
    unknown = "Not known until GitHub has been checked." if remote is None else ""
    check("ancestor", "Everything on GitHub is already on this computer", ancestor,
          ("GitHub has %d commit%s this computer does not have. Nothing will be pushed. A developer must bring "
           "them in from the terminal." % (behind, "" if behind == 1 else "s")) if behind else unknown)
    commits = gitops.commits_between(cfg, remote, local) if ancestor else []
    check("ahead", "At least one commit waiting to go live", commits,
          "GitHub already has every commit on this computer." if ancestor else unknown)
    working = working_changes(cfg)
    pub, files, riding, semantic, rows = [], {k: [] for k in KINDS}, [], [], []
    if commits:
        names = gitops.diff_names(cfg, remote, local)
        pub = [(s, p) for s, p in names if published(p)]
        room = room_for(cfg, local)
        check("clean_room", "The deploys' own rebuild of this commit gives the same files", room["ok"],
              ("Rebuilding it changes: " + ", ".join(room["changed"][:6])) if room["changed"]
              else "; ".join(room["problems"][:4]))
        for cid, label in PUBLISHED_CHECKS:
            hits = [f for f in room["found"] if f["id"] == cid]
            check(cid, label, not hits, "; ".join(f["message"] for f in hits[:5]))
        leaks = scan_secrets(cfg, remote, local, names)
        check("secrets", "No passwords, keys or tokens in what is sent", not leaks,
              "; ".join(f["message"] for f in leaks[:5]))
        sizes = gitops.tree(cfg, local)
        old_sizes = gitops.tree(cfg, remote) if any(s == "D" for s, _ in pub) else {}
        # dirty: the working tree's copy differs from the commit, so the local
        # preview would show something other than what goes live
        dirty = {it["path"] for g in GROUPS for it in working[g]}
        for s, p in pub:
            files[_kind_of(p)].append({"path": p, "change": CHANGE.get(s, "modified"), "dirty": p in dirty,
                                       "bytes": sizes.get(p, old_sizes.get(p))})
        riding = [{"path": p, "change": CHANGE.get(s, "modified"), "kind": _riding(p)}
                  for s, p in names if not published(p) and not CONTENT.match(p)]
        semantic = describe([p for _, p in names if CONTENT.match(p)],
                            lambda rel: gitops.show_file(cfg, remote, rel), lambda rel: gitops.show_file(cfg, local, rel))
        mine = admin_shas(cfg)
        for i, c in enumerate(commits):
            listed = [{"change": CHANGE.get(s, "modified"), "path": p} for s, p in gitops.commit_files(cfg, c["sha"])] if i < 50 else None
            rows.append(dict(c, short=c["sha"][:7], made_in_admin=c["sha"] in mine, files=listed))
    pending = admin_items(working)
    warnings = []
    if pending:
        warnings.append({"id": "uncommitted", "message": "These saved changes are not in a commit and will not go live.",
                         "count": len(pending), "paths": [it["path"] for it in pending[:12]]})
    ready = all(c["ok"] for c in checks)
    return {"preview_id": preview_id(app.token, local, remote, _files_digest(pub, commits)) if ready else None,
            "expires_in": PREVIEW_TTL if ready else None, "ready": ready,
            "local_sha": local, "remote_sha": remote, "fetched_at": fetched_iso(cfg), "branch": b,
            "commits": rows, "external": sum(1 for r in rows if not r["made_in_admin"]),
            "published_files": files, "published_count": len(pub), "semantic": semantic, "riding_along": riding,
            "checks": checks, "warnings": warnings, "no_push": cfg.no_push, "targets": ["Netlify", "GitHub Pages"]}


def check_preview(app, pid, local, remote):
    """A publish must follow a review made here, in the last ten minutes, of
    exactly these two shas, commits and published files. Returns the commits."""
    cfg = app.cfg
    try:
        issued = int(pid.split(".", 1)[0])
    except (AttributeError, ValueError):
        raise ApiError(412, "review_stale", "This publish does not match a review made here: review again.")
    if not 0 <= time.time() - issued <= PREVIEW_TTL:
        raise ApiError(412, "review_stale", "The review is more than ten minutes old: review again.")
    if gitops.resolve(cfg, local) != local or gitops.resolve(cfg, remote) != remote:
        raise ApiError(412, "review_stale", "Something changed since you reviewed: review again.")
    commits = gitops.commits_between(cfg, remote, local)
    pub = [(s, p) for s, p in gitops.diff_names(cfg, remote, local) if published(p)]
    if not hmac.compare_digest(preview_id(app.token, local, remote, _files_digest(pub, commits), issued), pid):
        raise ApiError(412, "review_stale", "Something changed since you reviewed: review again.")
    return commits


def push_failure(res):
    """A rejected push in the owner's words. Nothing is retried."""
    low = (" ".join(r["summary"] for r in res["refs"]) + " " + res["stderr"]).lower()
    if "non-fast-forward" in low or "fetch first" in low:
        return ("GitHub has commits this computer does not have, so nothing was published. A developer must bring "
                "them in from Terminal.")
    if "authentication" in low or "could not read username" in low or "permission denied" in low:
        return ("GitHub did not accept this computer's sign-in, so nothing was published. Push once from Terminal "
                "so the keychain has it, then try again.")
    if "could not resolve host" in low or "unable to access" in low or "timed out" in low:
        return "GitHub could not be reached, so nothing was published."
    return "GitHub refused the push, so nothing was published."


def go_live(app, local, remote, include_external, log):
    """The push job: fetch again and stop if anything moved since the review,
    push the reviewed sha (fast-forward only), fetch once more to confirm,
    and log it."""
    cfg = app.cfg
    log("Checking GitHub again")
    now = gitops.fetch(cfg)
    note_fetch(cfg, now)
    if now != remote or gitops.resolve(cfg, "HEAD") != local:
        raise ApiError(412, "review_stale", "Something changed since you reviewed: review again.",
                       {"remote_sha": now, "local_sha": gitops.resolve(cfg, "HEAD")})
    if not gitops.is_ancestor(cfg, remote, local):
        raise ApiError(409, "not_fast_forward", "GitHub has commits this computer does not have. Nothing was pushed.")
    commits = gitops.commits_between(cfg, remote, local)
    mine = admin_shas(cfg)
    outside = [c for c in commits if c["sha"] not in mine]
    if outside and include_external is not True:
        raise ApiError(422, "confirm_external", "Tick the box for the %d commit%s made outside the admin: %s too."
                       % (len(outside), "" if len(outside) == 1 else "s", "it goes live" if len(outside) == 1 else "they go live"))
    log("Sending %s to GitHub" % local[:7])
    res = gitops.push(cfg, local)
    if not res["ok"]:
        raise ApiError(502, "push_failed", push_failure(res), {"stderr": res["stderr"][-500:], "refs": res["refs"]})
    log("Checking that GitHub has it")
    try:
        after = gitops.fetch(cfg)
        note_fetch(cfg, after)
    except ApiError:
        after = None
    append_log(cfg, {"kind": "publish", "sha": local, "remote_before": remote, "remote_after": after,
                     "commits": len(commits), "outside": len(outside), "actor": app.store.actor})
    return {"sha": local, "short": local[:7], "remote_before": remote, "remote_after": after,
            "confirmed": after == local, "commits": len(commits),
            "message": "Netlify and GitHub Pages have started deploying."}
