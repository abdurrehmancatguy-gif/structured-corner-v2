"""Git: reading history, committing the admin's own files, and going live.

Every call runs git from a fixed argv with a clean environment: C locale and
-z output so file names and subjects parse the same on every machine,
core.quotepath off so non-ASCII names come through as they are, no pager, no
colour, GIT_OPTIONAL_LOCKS=0 so a read never takes the index lock a
terminal's own git might be waiting for, stdin closed and a timeout. A
commit id must look like one before it reaches git, so nothing a request
sends can be read as an option.

Three allow-lists keep the kinds apart: run() reads, write() only adds and
commits named paths (never --amend or -a), and the network calls are the
two functions fetch() and push(). Nothing here pulls, merges, rebases,
resets, stashes, checks out, tags or changes config. push() sends one
reviewed sha to refs/heads/main with an argv built from constants, and a
guard refuses anything that could force or delete, even if a later change
tried to add it.
"""
import hashlib
import io
import os
import pathlib
import re
import secrets
import shutil
import subprocess
import tarfile
import time

from . import tools
from .errors import ApiError

SHA = re.compile(r"^[0-9a-f]{7,40}$")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
CONTENT = re.compile(r"^flow/content/[a-z0-9_-]+\.json$")
READ_ONLY = ("log", "show", "rev-parse", "status", "diff", "merge-base", "ls-tree", "archive")
WRITES = ("add", "commit")
COMMIT_REFUSED = ("--amend", "-a", "--all", "--fixup", "--squash", "--allow-empty", "-i", "--include")
PUSH_REFUSED = ("--force", "-f", "--force-with-lease", "--force-if-includes", "--mirror", "--delete", "-d", "--prune", "--all")
REMOTE_MAIN = "refs/remotes/origin/main"
TIMEOUT = 20
FETCH_TIMEOUT = 60
PUSH_TIMEOUT = 120
_GIT = None


def git_path():
    global _GIT
    if _GIT is None:
        _GIT = shutil.which("git", path="/usr/bin:/opt/homebrew/bin:/usr/local/bin:/bin") or ""
    return _GIT


def _env(network=False):
    keys = ("PATH", "HOME", "TMPDIR") + (("USER", "LOGNAME", "SSH_AUTH_SOCK") if network else ())
    env = {k: os.environ[k] for k in keys if k in os.environ}
    env.update(LC_ALL="C", LANG="C", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat")
    if network:
        # The admin never asks for a password: with no stored credentials the
        # fetch or push fails at once and the owner is told to use Terminal.
        env.update(GIT_ASKPASS="/usr/bin/false", SSH_ASKPASS="/usr/bin/false")
    return env


def _spawn(cmd, cwd, env, timeout):
    """The one place git is started, so a test can see every argv."""
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ApiError(502, "tool_failed", "Git took longer than %d s and was stopped." % timeout)
    except OSError as e:
        raise ApiError(502, "tool_failed", "Git could not start: %s" % e.strerror)
    return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")[-2000:]


def _git(cfg, args, timeout, network=False):
    if not git_path():
        raise ApiError(503, "unavailable", "Git is not installed on this computer.")
    cmd = [git_path(), "--no-pager", "-c", "core.quotepath=off", "-c", "color.ui=false",
           "-c", "log.showSignature=false"] + list(args)
    return _spawn(cmd, str(cfg.repo), _env(network), timeout)


def check_sha(sha):
    if not isinstance(sha, str) or not SHA.match(sha):
        raise ApiError(400, "bad_request", "That is not a commit id.")
    return sha


def check_full_sha(sha):
    if not isinstance(sha, str) or not FULL_SHA.match(sha):
        raise ApiError(400, "bad_request", "That is not a full commit id.")
    return sha


def available(cfg):
    """Whether the repository the admin serves is a git checkout it can read."""
    return bool(git_path()) and (cfg.repo / ".git").exists()


def run(cfg, args, timeout=TIMEOUT):
    """git <args> in the served repository, read-only subcommands only.
    Returns (exit code, stdout bytes, stderr text). A git that cannot start
    or takes too long is a 502."""
    if not args or args[0] not in READ_ONLY:
        raise ValueError("not a read-only git command: %r" % (args[:1],))
    return _git(cfg, args, timeout)


def write(cfg, args, timeout=60):
    """git add or git commit --only, always with the paths after --."""
    if not args or args[0] not in WRITES or "--" not in args:
        raise ValueError("not an allowed git write: %r" % (args[:1],))
    opts = args[1:args.index("--")]
    if args[0] == "commit" and ("--only" not in opts or any(a in COMMIT_REFUSED for a in opts)):
        raise ValueError("an admin commit names its paths with --only and nothing else: %r" % opts)
    return _git(cfg, args, timeout)


def _fields(out, n):
    """Split -z output made of NUL-separated fields, n per record."""
    parts = out.decode("utf-8", "replace").split("\0")
    if parts and parts[-1] == "":
        parts.pop()
    return [parts[i:i + n] for i in range(0, len(parts) - n + 1, n)]


def log_file(cfg, rel, limit=30):
    """The commits that changed one content file, newest first:
    [{sha, at, subject}]. An empty list when the file has no history."""
    if not CONTENT.match(rel):
        raise ValueError("not a content file: %r" % rel)
    code, out, err = run(cfg, ["log", "-z", "--format=%H%x00%aI%x00%s", "--max-count=%d" % int(limit), "--", rel])
    if code != 0:
        if "does not have any commits" in err:
            return []
        raise ApiError(502, "tool_failed", "Git could not read the history.", {"stderr": err[-500:]})
    return [{"sha": s, "at": at, "subject": subj} for s, at, subj in _fields(out, 3)]


def commit(cfg, sha):
    """One commit's {sha, at, subject}, or None when there is no such commit."""
    check_sha(sha)
    code, out, _ = run(cfg, ["log", "-z", "-1", "--format=%H%x00%aI%x00%s", sha + "^{commit}", "--"])
    rows = _fields(out, 3) if code == 0 else []
    return {"sha": rows[0][0], "at": rows[0][1], "subject": rows[0][2]} if rows else None


def show_file(cfg, sha, rel):
    """The bytes of a content file as committed at sha, or None when the file
    did not exist there (or there is no such commit)."""
    check_sha(sha)
    if not CONTENT.match(rel):
        raise ValueError("not a content file: %r" % rel)
    code, out, _ = run(cfg, ["show", "%s:%s" % (sha, rel)])
    return out if code == 0 else None


# ---- the working tree and the branch ------------------------------------------

OPERATIONS = (("MERGE_HEAD", "a merge"), ("rebase-merge", "a rebase"), ("rebase-apply", "a rebase"),
              ("CHERRY_PICK_HEAD", "a cherry-pick"), ("REVERT_HEAD", "a revert"), ("BISECT_LOG", "a bisect"))


def _fail(err, what):
    return ApiError(502, "tool_failed", "Git could not %s." % what, {"stderr": err[-500:]})


def status(cfg):
    """[(xy, path)] from git status --porcelain=v1 -z --untracked-files=all.
    Renames come as a deletion and an addition, so each path is judged on
    its own."""
    code, out, err = run(cfg, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"])
    if code != 0:
        raise _fail(err, "list the changes")
    return [(rec[:2], rec[3:]) for rec in out.decode("utf-8", "replace").split("\0") if len(rec) > 3]


def resolve(cfg, ref):
    """The full sha HEAD, origin/main or a given sha stands for, or None."""
    if ref not in ("HEAD", REMOTE_MAIN):
        check_full_sha(ref)
    code, out, _ = run(cfg, ["rev-parse", "--verify", "-q", ref + "^{commit}"])
    s = out.decode("ascii", "replace").strip()
    return s if code == 0 and FULL_SHA.match(s) else None


def branch(cfg):
    """The checked-out branch's name, or None when HEAD is detached."""
    code, out, _ = run(cfg, ["rev-parse", "--symbolic-full-name", "HEAD"])
    name = out.decode("utf-8", "replace").strip()
    return name[len("refs/heads/"):] if code == 0 and name.startswith("refs/heads/") else None


def git_dir(cfg):
    code, out, _ = run(cfg, ["rev-parse", "--absolute-git-dir"])
    return pathlib.Path(out.decode("utf-8", "replace").strip()) if code == 0 else None


def in_progress(cfg):
    """The operation a terminal left half-done (a merge, a rebase), or None."""
    d = git_dir(cfg)
    for name, what in OPERATIONS:
        if d is not None and (d / name).exists():
            return what
    return None


def index_locked(cfg):
    """True while a terminal's git holds the index. The lock is only ever
    reported: removing it could break the git that holds it."""
    d = git_dir(cfg)
    return d is not None and (d / "index.lock").exists()


def blob_sha(path):
    """The id git would give the file's bytes, or None when there is no file."""
    try:
        data = pathlib.Path(path).read_bytes()
    except (FileNotFoundError, IsADirectoryError, NotADirectoryError):
        return None
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def commit_paths(cfg, message, paths, new_paths=()):
    """git add -- <new paths>, then git commit --only -- <paths>: exactly those
    paths go in, and anything a developer staged stays staged and out of it.
    Returns the new commit's sha."""
    if new_paths:
        code, _, err = write(cfg, ["add", "--"] + list(new_paths))
        if code != 0:
            raise _commit_error(err)
    code, _, err = write(cfg, ["commit", "--only", "--quiet", "--message=" + message, "--"] + list(paths))
    if code != 0:
        raise _commit_error(err)
    return resolve(cfg, "HEAD")


def _commit_error(err):
    if "index.lock" in err:
        return ApiError(409, "git_locked", "Git is busy in a terminal, so nothing was committed. Try again when it has "
                        "finished. If no git is running, a developer can check the repository from Terminal.")
    if "tell me who you are" in err or "user.email" in err:
        return ApiError(422, "no_identity", "Git does not know who is committing on this computer. Set user.name and "
                        "user.email once from Terminal, then commit again.")
    return ApiError(502, "commit_failed", "Git did not make the commit.", {"stderr": err[-500:]})


# ---- comparing commits ------------------------------------------------------------

def tree(cfg, sha, prefix="flow"):
    """{path: size} of every file committed at sha under prefix."""
    check_full_sha(sha)
    code, out, err = run(cfg, ["ls-tree", "-r", "-z", "-l", "--full-tree", sha, prefix])
    if code != 0:
        raise _fail(err, "list the commit's files")
    files = {}
    for rec in out.decode("utf-8", "replace").split("\0"):
        meta, _, path = rec.partition("\t")
        bits = meta.split()
        if len(bits) == 4 and bits[1] == "blob":
            files[path] = int(bits[3]) if bits[3].isdigit() else 0
    return files


def diff_names(cfg, a, b, paths=()):
    """[(status letter, path)] from commit a to commit b; renames come as a
    deletion and an addition."""
    check_full_sha(a)
    check_full_sha(b)
    code, out, err = run(cfg, ["diff", "--name-status", "-z", "--no-renames", a, b, "--"] + list(paths))
    if code != 0:
        raise _fail(err, "compare the commits")
    parts = out.decode("utf-8", "replace").split("\0")
    return [(parts[i][:1], parts[i + 1]) for i in range(0, len(parts) - 1, 2) if parts[i]]


def diff_text(cfg, a, b, limit=32 * 1024 * 1024):
    """The patch from a to b, for the secret scan: binary files show only as
    "Binary files differ"."""
    check_full_sha(a)
    check_full_sha(b)
    code, out, err = run(cfg, ["diff", "--no-ext-diff", "--no-textconv", "-U0", a, b, "--"], timeout=60)
    if code != 0:
        raise _fail(err, "compare the commits")
    return out[:limit].decode("utf-8", "replace")


def commits_between(cfg, base, head, limit=200):
    """[{sha, author, at, subject}] in head and not in base, newest first."""
    check_full_sha(base)
    check_full_sha(head)
    code, out, err = run(cfg, ["log", "-z", "--format=%H%x00%an%x00%aI%x00%s", "--max-count=%d" % int(limit),
                               "%s..%s" % (base, head), "--"])
    if code != 0:
        raise _fail(err, "list the commits")
    return [{"sha": s, "author": a, "at": at, "subject": subj} for s, a, at, subj in _fields(out, 4)]


def commit_files(cfg, sha):
    """[(status letter, path)] one commit changed."""
    check_full_sha(sha)
    code, out, err = run(cfg, ["show", "-z", "--no-renames", "--name-status", "--format=", sha, "--"])
    if code != 0:
        raise _fail(err, "read the commit")
    parts = out.decode("utf-8", "replace").lstrip("\n").split("\0")
    return [(parts[i][:1], parts[i + 1]) for i in range(0, len(parts) - 1, 2) if parts[i]]


def is_ancestor(cfg, a, b):
    """True when commit a is already part of commit b's history."""
    check_full_sha(a)
    check_full_sha(b)
    return run(cfg, ["merge-base", "--is-ancestor", a, b])[0] == 0


# ---- GitHub -----------------------------------------------------------------------

def fetch(cfg):
    """git fetch --no-tags origin main. Returns origin/main's sha now. Fails
    at once, with no prompt, when GitHub cannot be reached or asks who we are."""
    code, _, err = _git(cfg, ["fetch", "--no-tags", "--quiet", "origin", "main"], FETCH_TIMEOUT, network=True)
    if code != 0:
        raise ApiError(502, "fetch_failed", "GitHub could not be reached, so nothing can be published right now.",
                       {"stderr": err[-500:]})
    return resolve(cfg, REMOTE_MAIN)


def check_push_args(argv):
    """Refuse anything that could force, delete or send more than one ref.
    push_argv() never adds such an argument; this makes sure no later edit can."""
    if not argv or argv[0] != "push":
        raise ValueError("not a push: %r" % (argv[:1],))
    for a in argv[1:]:
        short = a.startswith("-") and not a.startswith("--")
        if (a.startswith("+") or a.startswith(":") or a in PUSH_REFUSED
                or any(a.startswith(p + "=") for p in PUSH_REFUSED if p.startswith("--"))
                or (short and any(c in a[1:] for c in "fd"))):
            raise ValueError("refused push argument: %r" % a)
    return argv


def push_argv(sha):
    """The whole argv of a publish: the reviewed sha, never a branch name, so
    exactly what was reviewed goes live even if main moves meanwhile."""
    check_full_sha(sha)
    return check_push_args(["push", "--porcelain", "--no-tags", "origin", "%s:refs/heads/main" % sha])


def push(cfg, sha):
    """Push sha to GitHub's main, fast-forward only (git refuses anything
    else without a force, and there is none). Returns {ok, argv, refs,
    stderr}; a rejection is reported, never retried."""
    argv = check_push_args(push_argv(sha))
    code, out, err = _git(cfg, argv, PUSH_TIMEOUT, network=True)
    refs = []
    for line in out.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and len(parts[0]) == 1:
            refs.append({"flag": parts[0], "ref": parts[1], "summary": parts[2]})
    # " " fast-forward, "*" a new branch, "=" already there; "!" rejected
    ok = code == 0 and bool(refs) and all(r["flag"] in (" ", "*", "=") for r in refs)
    return {"ok": ok, "argv": argv, "refs": refs, "stderr": err[-800:]}


# ---- the clean room ------------------------------------------------------------------

def _extract(data, root):
    """Unpack git archive's tar into root: plain files and folders with names
    inside root only. Returns the names of anything else, which is skipped."""
    odd = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tf:
        for m in tf:
            parts = [p for p in m.name.split("/") if p]
            if m.name.startswith("/") or ".." in parts or not parts:
                odd.append(m.name)
                continue
            dest = root.joinpath(*parts)
            if m.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif m.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(m) as src, open(str(dest), "wb") as out:
                    shutil.copyfileobj(src, out)
                if m.mode & 0o111:
                    os.chmod(str(dest), 0o755)
            else:
                odd.append(m.name)
    return odd


def _hashes(root):
    out = {}
    for d, dirs, files in os.walk(str(root)):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for f in files:
            p = os.path.join(d, f)
            h = hashlib.sha1()
            with open(p, "rb") as fh:
                for chunk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(chunk)
            out[os.path.relpath(p, str(root))] = h.hexdigest()
    return out


def _room(ok, t0, changed=(), problems=(), found=()):
    return {"ok": ok, "changed": list(changed), "problems": list(problems), "found": list(found),
            "ms": int((time.monotonic() - t0) * 1000)}


def clean_room(cfg, sha, overlay=(), inspect=None):
    """What the deploys will find, checked before it happens: flow/ as
    committed at sha, each overlay path (repo-relative, under flow/) copied in
    from the working tree or deleted when the working tree no longer has it,
    then build.py, then every file compared. Any changed or new file is what
    the deploys' own "git status --porcelain" check would stop on.

    inspect(flow_dir) may look at the files before the build and returns a
    list of findings. Returns {ok, changed, problems, found, ms}. The folder
    (flow/content/.backups/verify/<id>) is always removed afterwards."""
    check_full_sha(sha)
    t0 = time.monotonic()
    root = cfg.backups / "verify" / ("%s-%s" % (time.strftime("%Y%m%d-%H%M%S"), secrets.token_hex(3)))
    root.mkdir(parents=True)
    try:
        code, out, err = run(cfg, ["archive", "--format=tar", sha, "flow"], timeout=60)
        if code != 0:
            return _room(False, t0, problems=["Git could not export the commit: " + err[-300:]])
        odd = _extract(out, root)
        if odd:
            return _room(False, t0, problems=["The commit holds something other than plain files: " + ", ".join(odd[:5])])
        for rel in overlay:
            parts = rel.split("/")
            if parts[0] != "flow" or any(p in ("", ".", "..") for p in parts):
                raise ValueError("not a path under flow/: %r" % rel)
            src, dst = cfg.repo / rel, root / rel
            if src.is_file() and not src.is_symlink():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(str(src), str(dst))
            elif dst.is_file():
                dst.unlink()
        flow = root / "flow"
        found = inspect(flow) if inspect else []
        before = _hashes(flow)
        build = tools.run(cfg, "build", cwd=flow)
        if not build["ok"]:
            return _room(False, t0, problems=build["problems"], found=found)
        after = _hashes(flow)
        changed = sorted("flow/" + p for p in set(before) | set(after) if before.get(p) != after.get(p))
        return _room(not changed, t0, changed=changed, found=found)
    finally:
        shutil.rmtree(str(root), ignore_errors=True)
