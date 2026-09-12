"""The storefront's own tools, run from a fixed table.

Only build.py and make_derivatives.py, with a fixed argv, a clean
environment and timeouts; never the importers, which read folders outside
the repo and rewrite products.json wholesale. After a run the flow/ tree is
compared with how it was before, so a tool that touched anything outside its
own outputs fails the save instead of slipping through.
"""
import os
import subprocess
import time

TOOLS = {
    "build": (["build.py"], 60),
    "derivatives": (["tools/make_derivatives.py"], 300),
}


def _env():
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR") if k in os.environ}
    env.update(LANG="en_US.UTF-8", LC_ALL="en_US.UTF-8", PYTHONDONTWRITEBYTECODE="1")
    return env


def _problems(stderr):
    """build.py exits with 'build failed:' and one problem per line."""
    lines = [l.strip() for l in (stderr or "").splitlines() if l.strip()]
    if "build failed:" in lines:
        return lines[lines.index("build failed:") + 1:]
    return lines[-5:] or ["The tool stopped without saying why."]


def run(cfg, name):
    args, timeout = TOOLS[name]
    t0 = time.monotonic()
    try:
        p = subprocess.run([cfg.python] + args, cwd=str(cfg.flow), env=_env(),
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "ms": timeout * 1000, "problems": ["%s took longer than %d s and was stopped." % (name, timeout)]}
    ms = int((time.monotonic() - t0) * 1000)
    ok = p.returncode == 0
    return {"ok": ok, "ms": ms, "problems": [] if ok else _problems(p.stderr), "out": (p.stdout or "")[-2000:]}


def scan(flow):
    """size and mtime of every file under flow/, less the admin's own backups."""
    out = {}
    root = str(flow)
    for d, dirs, files in os.walk(root):
        rel = os.path.relpath(d, root)
        dirs[:] = [x for x in dirs if not x.startswith(".") and x != "__pycache__"
                   and not (rel == "content" and x == ".backups")]
        for f in files:
            p = os.path.join(d, f)
            try:
                st = os.lstat(p)
            except FileNotFoundError:
                continue
            out[os.path.normpath(os.path.join(rel, f))] = (st.st_size, st.st_mtime_ns)
    return out


def unexpected(before, after, allowed):
    changed = {p for p in set(before) | set(after) if before.get(p) != after.get(p)}
    return sorted(changed - set(allowed))
