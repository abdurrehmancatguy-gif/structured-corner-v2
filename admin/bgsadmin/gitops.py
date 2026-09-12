"""Git, read-only for now: the committed versions of a content file.

Every call runs git from a fixed argv with a clean environment: C locale and
-z output so file names and subjects parse the same on every machine,
core.quotepath off so non-ASCII names come through as they are, no pager, no
colour, GIT_OPTIONAL_LOCKS=0 so a read never takes the index lock a
terminal's own git might be waiting for, and a timeout. Only the read-only
subcommands below can run from here. A commit id must look like one before
it reaches git, so nothing a request sends can be read as an option.

Committing and pushing (publish) are added by that stage, beside these, with
the same runner.
"""
import os
import re
import shutil
import subprocess

from .errors import ApiError

SHA = re.compile(r"^[0-9a-f]{7,40}$")
CONTENT = re.compile(r"^flow/content/[a-z0-9_-]+\.json$")
READ_ONLY = ("log", "show", "rev-parse")
TIMEOUT = 20
_GIT = None


def git_path():
    global _GIT
    if _GIT is None:
        _GIT = shutil.which("git", path="/usr/bin:/opt/homebrew/bin:/usr/local/bin:/bin") or ""
    return _GIT


def _env():
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
    env.update(LC_ALL="C", LANG="C", GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0", GIT_PAGER="cat")
    return env


def check_sha(sha):
    if not isinstance(sha, str) or not SHA.match(sha):
        raise ApiError(400, "bad_request", "That is not a commit id.")
    return sha


def available(cfg):
    """Whether the repository the admin serves is a git checkout it can read."""
    return bool(git_path()) and (cfg.repo / ".git").exists()


def run(cfg, args, timeout=TIMEOUT):
    """git <args> in the served repository. Returns (exit code, stdout bytes,
    stderr text). A git that cannot start or takes too long is a 502."""
    if not args or args[0] not in READ_ONLY:
        raise ValueError("not a read-only git command: %r" % (args[:1],))
    if not git_path():
        raise ApiError(503, "unavailable", "Git is not installed on this computer.")
    cmd = [git_path(), "--no-pager", "-c", "core.quotepath=off", "-c", "color.ui=false",
           "-c", "log.showSignature=false"] + list(args)
    try:
        p = subprocess.run(cmd, cwd=str(cfg.repo), env=_env(), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ApiError(502, "tool_failed", "Git took longer than %d s and was stopped." % timeout)
    except OSError as e:
        raise ApiError(502, "tool_failed", "Git could not start: %s" % e.strerror)
    return p.returncode, p.stdout, p.stderr.decode("utf-8", "replace")[-500:]


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
        raise ApiError(502, "tool_failed", "Git could not read the history.", {"stderr": err})
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
