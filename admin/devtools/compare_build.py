"""Compare the storefront build in this working tree with the one committed
at a base revision, to prove that moving text out of build.py or shop.js into
content left the pages as they were.

    cd flow && /usr/bin/python3 build.py && cd ..
    /usr/bin/python3 admin/devtools/compare_build.py [BASE]        # BASE defaults to HEAD

Every generated file is compared after two normalizations that change
nothing a visitor gets: ?v=<hash> tokens are dropped (they follow file
contents) and HTML entities are decoded (&middot; and the character itself
are the same text). catalogue.js is compared global by global:
BGS_CATALOGUE and BGS_IMGV must match; any other window.* global is listed
as added or changed, which is expected when content wiring adds data.
Exit status 0 when nothing differs, 1 otherwise.
"""
import difflib
import html
import json
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "admin"))
from bgsadmin.config import PAGES  # noqa: E402

FILES = list(PAGES) + ["404.html", "robots.txt", "assets/flow.min.css", "tools/derivatives.json"]
V = re.compile(r"\?v=[0-9a-f]+")
MAX_LINES = 60
FIXED = ("BGS_CATALOGUE", "BGS_IMGV")


def committed(base, rel):
    p = subprocess.run(["git", "show", "%s:flow/%s" % (base, rel)], cwd=str(REPO), capture_output=True)
    return p.stdout.decode("utf-8") if p.returncode == 0 else None


def norm(text):
    return html.unescape(V.sub("?v=", text))


def lines(text):
    # the pages carry few newlines; break between tags so a diff points at the element
    return re.sub(r">\s*<", ">\n<", text).splitlines()


def js_globals(js):
    out = {}
    for line in js.splitlines():
        m = re.match(r"window\.([A-Za-z_]\w*) = (.*);$", line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def show_diff(a, b, name_a, name_b):
    diff = list(difflib.unified_diff(lines(a), lines(b), name_a, name_b, n=1, lineterm=""))
    print("\n".join(diff[:MAX_LINES]))
    if len(diff) > MAX_LINES:
        print("... %d more diff lines" % (len(diff) - MAX_LINES))


def catalogue_diff(old, new):
    """Where two catalogues differ, product by product and field by field."""
    out = []
    for pid in sorted(set(old) | set(new)):
        a, b = old.get(pid), new.get(pid)
        if a == b:
            continue
        if a is None or b is None:
            out.append("%s: %s" % (pid, "added" if a is None else "removed"))
            continue
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                out.append("%s.%s: %r -> %r" % (pid, k, a.get(k), b.get(k)))
    return out


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    flow = REPO / "flow"
    bad = 0
    for rel in FILES:
        old = committed(base, rel)
        p = flow / rel
        new = p.read_text(encoding="utf-8") if p.exists() else None
        if old is None and new is None:
            continue
        if old is None or new is None:
            print("%s: %s" % (rel, "new file" if old is None else "missing now"))
            bad += 1
            continue
        a, b = norm(old), norm(new)
        if a != b:
            bad += 1
            show_diff(a, b, "%s@%s" % (rel, base), rel + " (working tree)")
    og = js_globals(committed(base, "assets/catalogue.js") or "")
    ng = js_globals((flow / "assets" / "catalogue.js").read_text(encoding="utf-8"))
    for name in FIXED:
        try:
            a, b = json.loads(og.get(name, "null")), json.loads(ng.get(name, "null"))
        except ValueError:
            a, b = og.get(name), ng.get(name)
        if a != b:
            bad += 1
            print("catalogue.js: window.%s differs" % name)
            if isinstance(a, dict) and isinstance(b, dict) and name == "BGS_CATALOGUE":
                for line in catalogue_diff(a, b)[:30]:
                    print("  " + line)
    for name in sorted(set(og) | set(ng)):
        if name in FIXED:
            continue
        if name not in og:
            print("catalogue.js: adds window.%s (%d bytes)" % (name, len(ng[name])))
        elif name not in ng:
            print("catalogue.js: no longer has window.%s" % name)
            bad += 1
        elif og[name] != ng[name]:
            print("catalogue.js: window.%s changed" % name)
    print("identical after normalization" if not bad else "%d difference(s) against %s" % (bad, base))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
