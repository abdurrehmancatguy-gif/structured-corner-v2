#!/usr/bin/env python3
"""
BGS Corner - local admin
========================

Edits the content layer in flow/content/ and regenerates the site.

Runs on the standard library only: no npm, no pip, nothing to install. Start it
with

    python3 admin/server.py            # from flow/, serves on 4311

and leave the storefront's own server running on 4310 in another tab. Saving
here rewrites the JSON and immediately re-runs build.py, so a reload of 4310
shows the change.

WHERE THIS IS GOING
-------------------
Content is stored as collections of documents, which is the shape Firestore
wants. Everything that touches storage is behind the Store class below, so
swapping the JSON files for Firestore later means writing one new Store, not
rewriting the admin or the build. Nothing here talks to the network.

SCOPE
-----
Local only, and deliberately so: it binds to 127.0.0.1, has no login, and is
not safe to expose. It is the editing tool, not the live backend.
"""

import http.server, socketserver, json, pathlib, subprocess, sys, urllib.parse, shutil, datetime

ROOT        = pathlib.Path(__file__).resolve().parent.parent   # flow/
CONTENT_DIR = ROOT / "content"
BACKUP_DIR  = ROOT / "content" / ".backups"
ADMIN_DIR   = pathlib.Path(__file__).resolve().parent
PORT        = 4311

# only these may be read or written, so a crafted path cannot reach the disk
COLLECTIONS = {
    "products":   "Products",
    "settings":   "Store settings",
    "navigation": "Navigation and footer",
    "copy":       "Site copy",
    "home":       "Home page",
}


class Store:
    """Every read and write goes through here.

    The Firestore version of this class keeps the same four methods and the
    same document shape; nothing above it needs to change."""

    def list(self):
        return list(COLLECTIONS)

    def get(self, name):
        if name not in COLLECTIONS:
            raise KeyError(name)
        return json.loads((CONTENT_DIR / (name + ".json")).read_text())

    def put(self, name, data):
        if name not in COLLECTIONS:
            raise KeyError(name)
        path = CONTENT_DIR / (name + ".json")
        self._backup(path)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def backups(self, name):
        """Every save is kept. This lists what can be rolled back to."""
        if not BACKUP_DIR.exists():
            return []
        out = []
        for f in sorted(BACKUP_DIR.glob(name + ".*.json"), reverse=True):
            stamp = f.stem.split(".", 1)[1]
            out.append({"file": f.name, "stamp": stamp,
                        "bytes": f.stat().st_size})
        return out

    def restore(self, name, filename):
        if name not in COLLECTIONS or "/" in filename or ".." in filename:
            raise KeyError(name)
        src = BACKUP_DIR / filename
        if not src.exists() or not src.name.startswith(name + "."):
            raise KeyError(filename)
        data = json.loads(src.read_text())
        self.put(name, data)
        return data

    def export_all(self):
        return {name: self.get(name) for name in COLLECTIONS}

    def import_all(self, bundle):
        written = []
        for name, data in bundle.items():
            if name in COLLECTIONS:
                self.put(name, data)
                written.append(name)
        return written

    def _backup(self, path):
        """Keep the last 20 versions of each file. Local undo, no git needed."""
        if not path.exists():
            return
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        shutil.copy2(path, BACKUP_DIR / ("%s.%s.json" % (path.stem, stamp)))
        old = sorted(BACKUP_DIR.glob(path.stem + ".*.json"))
        for f in old[:-20]:
            f.unlink()


STORE = Store()


def rebuild():
    """Regenerate the site. Returns (ok, output) rather than raising, so a
       broken edit shows up in the admin instead of killing the server."""
    try:
        r = subprocess.run([sys.executable, "build.py"], cwd=str(ROOT),
                           capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as e:
        return False, str(e)


class Handler(http.server.SimpleHTTPRequestHandler):
    def _send(self, code, payload, ctype="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/index.html"):
            return self._send(200, (ADMIN_DIR / "admin.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/api/collections":
            return self._send(200, {"collections": [{"id": k, "label": v} for k, v in COLLECTIONS.items()]})
        if path.startswith("/api/backups/"):
            name = path.rsplit("/", 1)[-1]
            return self._send(200, {"backups": STORE.backups(name)})
        if path == "/api/export":
            body = json.dumps(STORE.export_all(), indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition",
                             'attachment; filename="bgs-content-export.json"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if path.startswith("/api/content/"):
            name = path.rsplit("/", 1)[-1]
            try:
                return self._send(200, STORE.get(name))
            except KeyError:
                return self._send(404, {"error": "unknown collection"})
        return self._send(404, {"error": "not found"})

    def do_PUT(self):
        path = urllib.parse.urlparse(self.path).path
        if not path.startswith("/api/content/"):
            return self._send(404, {"error": "not found"})
        name = path.rsplit("/", 1)[-1]
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n).decode("utf-8"))
        except Exception as e:
            return self._send(400, {"error": "bad json: %s" % e})
        try:
            STORE.put(name, data)
        except KeyError:
            return self._send(404, {"error": "unknown collection"})
        ok, out = rebuild()
        return self._send(200, {"saved": True, "built": ok, "output": out})

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n).decode("utf-8"))

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/restore":
            try:
                b = self._body()
                data = STORE.restore(b["collection"], b["file"])
            except KeyError as e:
                return self._send(404, {"error": "cannot restore: %s" % e})
            except Exception as e:
                return self._send(400, {"error": str(e)})
            ok, out = rebuild()
            return self._send(200, {"restored": True, "built": ok, "data": data})
        if path == "/api/import":
            try:
                written = STORE.import_all(self._body())
            except Exception as e:
                return self._send(400, {"error": str(e)})
            ok, out = rebuild()
            return self._send(200, {"imported": written, "built": ok, "output": out})
        if path == "/api/build":
            ok, out = rebuild()
            return self._send(200, {"built": ok, "output": out})
        return self._send(404, {"error": "not found"})

    def log_message(self, *a):
        pass          # the admin prints its own lines; keep the console quiet


if __name__ == "__main__":
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), Handler) as srv:
        print("BGS Corner admin  ->  http://localhost:%d" % PORT)
        print("storefront        ->  http://localhost:4310  (run server.py for that)")
        print("editing           ->  %s" % CONTENT_DIR)
        print("Ctrl-C to stop.")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")
