"""A temporary clone of the repository with the admin server running on it.

Every test module starts its own Box on its own port (4700 to 4799; 4310 is
the owner's preview), so modules can run side by side:

    from box import Box
    b = Box(4741)
    status, body = b.api("GET", "products")

The clone gets this working tree's flow/ copied over it, so tests exercise
uncommitted changes to build.py, shop.js and content as well; the admin code
always runs from this working tree. The server runs with --no-push, always.
"""
import http.client
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

ADMIN = pathlib.Path(__file__).resolve().parent.parent
REPO = ADMIN.parent


def _skip(_dir, names):
    return {n for n in names if n in (".backups", "__pycache__") or (n.startswith(".") and n.endswith(".tmp"))}


class Box:
    def __init__(self, port, overlay=True, args=()):
        self.port = int(port)
        self.tmp = tempfile.mkdtemp(prefix="bgsadmin-")
        self.repo = pathlib.Path(self.tmp) / "repo"
        subprocess.run(["git", "clone", "-q", str(REPO), str(self.repo)], check=True)
        if overlay:
            shutil.copytree(str(REPO / "flow"), str(self.repo / "flow"), dirs_exist_ok=True, ignore=_skip)
        self.proc = subprocess.Popen([sys.executable, str(ADMIN / "server.py"), "--port", str(self.port),
                                      "--repo", str(self.repo), "--no-push"] + list(args),
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        for _ in range(150):
            try:
                if self.raw("GET", "/")[0] == 200:
                    break
            except OSError:
                time.sleep(0.1)
        else:
            self.proc.terminate()
            raise RuntimeError("the admin server did not start: %s" % self.proc.stdout.read(4000).decode("utf-8", "replace"))
        st, _, body = self.raw("GET", "/admin/", headers={"Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document", "Sec-Fetch-Site": "none"})
        self.token = re.search(rb'name="admin-token" content="([^"]+)"', body).group(1).decode()

    def raw(self, method, path, body=None, headers=None, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=100)
        h = {"Host": host if host is not None else "localhost:%d" % self.port}
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        out = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return out

    def api(self, method, path, body=None, rev=None, token=True, origin=True, ctype="application/json", headers=None):
        """JSON in and out. bytes are sent as they are, typed with ctype, which
        is how an upload is sent."""
        h = {}
        if token:
            h["X-Admin-Token"] = self.token
        if origin and method not in ("GET", "HEAD"):
            h["Origin"] = "http://localhost:%d" % self.port
        data = None
        if body is not None:
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            h["Content-Type"] = ctype
        if rev:
            h["If-Match"] = '"%s"' % rev
        h.update(headers or {})
        st, hd, raw = self.raw(method, "/admin/api/v1/" + path, data, h)
        try:
            return st, (json.loads(raw) if raw else None)
        except ValueError:
            return st, raw

    def content(self, name):
        return json.loads((self.repo / "flow" / "content" / ("%s.json" % name)).read_text(encoding="utf-8"))

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        shutil.rmtree(self.tmp, ignore_errors=True)
