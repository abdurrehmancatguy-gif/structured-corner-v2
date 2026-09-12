"""Render the storefront pages in headless Chrome after their scripts ran,
once from a base revision and once from this working tree, and diff what a
visitor gets: text, links, image and video sources, labels and hints.

    /usr/bin/python3 admin/devtools/dom_diff.py [--base REV] [--only index,cart] [--width 1440] [--ports 4790,4791]

Both copies are served by admin/server.py --storefront-only on spare ports,
so nothing touches the owner's preview on 4310 or any content, and Chrome
runs with throwaway profiles. The same-day countdown is masked because it
moves with the clock. Run build.py in the working tree first. Exit status 0
when every page matches.
"""
import argparse
import concurrent.futures
import difflib
import html.parser
import json
import os
import pathlib
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
V = re.compile(r"\?v=[0-9a-f]+")
PORT = re.compile(r"(localhost|127\.0\.0\.1):\d+")
CLOCK = re.compile(r"\b\d{1,2}\s?h\s?\d{1,2}\s?m(in)?\b|\b\d{1,2}:\d{2}(:\d{2})?\b")
ATTRS = ("href", "src", "srcset", "poster", "alt", "aria-label", "placeholder", "title", "value", "content", "data-a", "hidden")
SKIP = {"script", "style", "noscript", "template"}


class Visible(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        a = dict(attrs)
        # the two copies run on different ports, which shop.js writes into the canonical link
        bits = ["%s=%s" % (k, PORT.sub(r"\1", V.sub("?v=", a[k] or ""))) for k in ATTRS if k in a]
        if bits:
            self.out.append("<%s %s>" % (tag, " ".join(bits)))

    def handle_endtag(self, tag):
        if tag in SKIP and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            t = " ".join(data.split())
            if t:
                self.out.append(CLOCK.sub("#clock", t))


def visible(dom):
    p = Visible()
    p.feed(dom)
    return p.out


def urls():
    prods = json.loads((REPO / "flow" / "content" / "products.json").read_text(encoding="utf-8"))
    first = {}
    for pid, d in sorted(prods.items(), key=lambda kv: kv[1].get("order") or 0):
        if d.get("published", True):
            first.setdefault(d.get("category"), pid)
    out = ["index.html", "collection.html", "collection.html?q=oud"]
    out += ["collection.html?cat=%s" % c for c in ("attars", "bakhoor", "edp", "gift-sets")]
    out += ["product.html?p=%s" % first[c] for c in ("attars", "edp", "bakhoor", "gift-sets") if c in first]
    out += ["gift-box.html", "cart.html", "checkout.html", "confirmed.html", "track-order.html",
            "account.html", "quiz.html", "corporate.html", "no-such-page.html"]
    return out


def export(base, dest):
    arch = subprocess.Popen(["git", "archive", "--format=tar", base, "flow"], cwd=str(REPO), stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(dest)], stdin=arch.stdout, check=True)
    arch.stdout.close()
    if arch.wait() != 0:
        raise SystemExit("git archive %s failed" % base)


def serve(repo, port):
    p = subprocess.Popen([sys.executable, str(REPO / "admin" / "server.py"), "--storefront-only",
                          "--repo", str(repo), "--port", str(port)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(100):
        try:
            req = urllib.request.Request("http://127.0.0.1:%d/" % port, headers={"Host": "localhost:%d" % port})
            urllib.request.urlopen(req, timeout=2).read()
            return p
        except OSError:
            time.sleep(0.1)
    p.terminate()
    raise SystemExit("the storefront server on port %d did not start" % port)


LIVE = set()                   # Chrome processes still running, killed on any exit


def dump(url, width, root):
    """The page's DOM once its scripts ran. Chrome 152 prints the DOM and then
    does not exit on this Mac, so the output is read up to </html> and that
    Chrome is killed."""
    prof = tempfile.mkdtemp(prefix="prof-", dir=root)
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           "--disable-extensions", "--disable-background-networking", "--disable-sync", "--mute-audio",
           "--hide-scrollbars", "--user-data-dir=" + prof, "--window-size=%d,1000" % width,
           "--virtual-time-budget=3000", "--dump-dom", url]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    LIVE.add(p)
    buf = b""
    sel = selectors.DefaultSelector()
    sel.register(p.stdout, selectors.EVENT_READ)
    end = time.monotonic() + 40
    try:
        while time.monotonic() < end:
            if sel.select(timeout=0.5):
                chunk = os.read(p.stdout.fileno(), 65536)
                if not chunk:
                    break
                buf += chunk
                if b"</html>" in buf[-400:]:
                    break
            elif p.poll() is not None:
                break
        else:
            buf += ("<p>Chrome timed out on %s</p>" % url).encode()
    finally:
        sel.close()
        p.kill()
        p.wait(5)
        LIVE.discard(p)
        shutil.rmtree(prof, ignore_errors=True)
    return buf.decode("utf-8", "replace")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD")
    ap.add_argument("--only", default="")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--ports", default="4790,4791")
    a = ap.parse_args()
    pa, pb = (int(x) for x in a.ports.split(","))
    pages = urls()
    if a.only:
        keep = [k.strip() for k in a.only.split(",") if k.strip()]
        pages = [u for u in pages if any(u.startswith(k) for k in keep)]
    root = pathlib.Path(tempfile.mkdtemp(prefix="domdiff-"))
    procs = []
    # a time limit (perl alarm) or a kill still runs the cleanup below, so no
    # server or Chrome outlives the run
    for sig in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: sys.exit(3))
    try:
        (root / "base").mkdir()
        export(a.base, root / "base")
        procs = [serve(root / "base", pa), serve(REPO, pb)]
        jobs = [(u, port) for u in pages for port in (pa, pb)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            got = dict(zip(jobs, ex.map(lambda j: dump("http://localhost:%d/%s" % (j[1], j[0]), a.width, root), jobs)))
        bad = 0
        for u in pages:
            x, y = visible(got[(u, pa)]), visible(got[(u, pb)])
            if x == y:
                continue
            bad += 1
            print("== %s" % u)
            diff = list(difflib.unified_diff(x, y, "base", "working tree", n=0, lineterm=""))
            print("\n".join(diff[2:42]))
            if len(diff) > 42:
                print("... %d more diff lines" % (len(diff) - 42))
        print("%d of %d pages match" % (len(pages) - bad, len(pages)))
        return 1 if bad else 0
    finally:
        for p in list(LIVE):
            p.kill()
        for p in procs:
            p.terminate()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
