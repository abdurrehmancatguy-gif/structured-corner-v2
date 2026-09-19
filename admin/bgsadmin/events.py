"""The admin's own log: who signed in, who was let in or refused, and every
change to people and roles.

Content changes are already recorded twice over, in the revisions and the
audit trail the database keeps, with the person's address on each since roles
arrived. This file is for the events that are not content: sign-ins, refused
sign-ins, sign-outs, and staff changes. Both stores have one, so it works
whether the admin is on the database or on the files.

It lives in admin/local/events.jsonl, outside git and outside flow/, one JSON
object per line, appended and flushed to the disk as it happens so a power cut
loses at most the line being written.

What is never written: passwords, tokens, cookies or keys (the admin holds no
passwords at all), and no address in full beyond the one doing the acting,
which is the point of the record. An address in a message is masked to its
first letter and its domain.

Retention is KEEP_DAYS. Nothing is deleted quietly: stats() reports the oldest
line, and the admin shows a notice when the oldest is within WARN_DAYS of
going, so a copy can be kept before it does.
"""
import datetime
import json
import os
import pathlib
import re

KEEP_DAYS = 60
WARN_DAYS = 7
NAME = "events.jsonl"
EMAIL = re.compile(r"\b([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")


def path_of(repo):
    return pathlib.Path(repo) / "admin" / "local" / NAME


def mask(text):
    """An address inside a message becomes a@example.com, so the log says who
    it was about without carrying everyone's address in full."""
    return EMAIL.sub(lambda m: "%s***@%s" % (m.group(1), m.group(2)), str(text or ""))


def now():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def append(repo, kind, message, actor=None, ok=True, extra=None):
    """One line. Never raises: a log that stops the admin working is worse
    than a line that is missing, and the caller is usually mid-request."""
    line = {"when": now(), "kind": kind, "actor": actor or "", "ok": bool(ok),
            "message": mask(message)}
    if extra:
        line.update({k: mask(v) if isinstance(v, str) else v for k, v in extra.items()})
    p = path_of(repo)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(str(p), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, sort_keys=True) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.chmod(str(p), 0o600)
    except OSError:
        pass
    return line


def read(repo, limit=200, kind=None, actor=None):
    """The newest lines first, filtered. A line that cannot be parsed is
    skipped rather than hiding the rest of the log."""
    p = path_of(repo)
    out = []
    try:
        with open(str(p), encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return out
    for raw in reversed(lines):
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if kind and item.get("kind") != kind:
            continue
        if actor and item.get("actor") != actor:
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def _age_days(when):
    try:
        t = datetime.datetime.fromisoformat(str(when))
    except ValueError:
        return None
    if t.tzinfo is None:
        t = t.replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - t).days


def stats(repo):
    """How much is kept, how old the oldest is, and whether it is close to
    going. The admin shows the notice; nothing is deleted by reading this."""
    p = path_of(repo)
    oldest = None
    count = 0
    try:
        with open(str(p), encoding="utf-8") as f:
            for raw in f:
                try:
                    item = json.loads(raw)
                except ValueError:
                    continue
                count += 1
                if oldest is None:
                    oldest = item.get("when")
    except OSError:
        return {"lines": 0, "oldest": None, "oldest_days": None, "keep_days": KEEP_DAYS,
                "expiring": False, "bytes": 0}
    age = _age_days(oldest) if oldest else None
    return {"lines": count, "oldest": oldest, "oldest_days": age, "keep_days": KEEP_DAYS,
            "expiring": bool(age is not None and age >= KEEP_DAYS - WARN_DAYS),
            "bytes": p.stat().st_size if p.exists() else 0}


def export(repo):
    """Every line as it stands, for the copy someone keeps before the oldest
    go. Bytes, so what is saved is exactly what was written."""
    p = path_of(repo)
    try:
        return p.read_bytes()
    except OSError:
        return b""


def prune(repo):
    """Drop the lines older than KEEP_DAYS. Called on start-up, never in the
    middle of a request, and it rewrites the file in one go so a crash leaves
    either the old file or the new one."""
    p = path_of(repo)
    if not p.exists():
        return 0
    keep, dropped = [], 0
    try:
        with open(str(p), encoding="utf-8") as f:
            for raw in f:
                try:
                    age = _age_days(json.loads(raw).get("when"))
                except ValueError:
                    keep.append(raw)
                    continue
                if age is not None and age > KEEP_DAYS:
                    dropped += 1
                else:
                    keep.append(raw)
    except OSError:
        return 0
    if not dropped:
        return 0
    tmp = p.with_suffix(".jsonl.tmp")
    try:
        tmp.write_text("".join(keep), encoding="utf-8")
        os.chmod(str(tmp), 0o600)
        os.replace(str(tmp), str(p))
    except OSError:
        return 0
    return dropped
