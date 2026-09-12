"""One threaded HTTP server for the storefront preview and the admin.

Threaded for the reason flow/server.py was: a browser's speculative
preconnect sends nothing, and on a single thread it blocked every request
queued behind it. TCPServer rather than HTTPServer, whose server_bind looks
up the host's FQDN and can stall on macOS.
"""
import contextlib
import http.server
import os
import socketserver
import sys
import traceback
import urllib.parse

from . import routes, security, static
from .config import LIMITS, UI
from .errors import ApiError
from .jsonutil import dumps, strict_loads
from .security import ADMIN_HEADERS

CHUNK = 64 * 1024


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, addr, handler, app):
        self.app = app
        super().__init__(addr, handler)

    def handle_error(self, request, client_address):
        # a browser leaving mid-download is not an error worth a traceback
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)


class Request:
    """What an API handler gets: the app, the parsed body and query, the route's
    named groups (already matched against their patterns) and the headers.

    On a raw-body route (an upload) the body has been typed and sized but not
    read: the handler takes it once, with save_body(path) to stream it to a
    file or read_body() for a small one."""

    def __init__(self, app, method, query, params, body, headers, upload=None):
        self.app = app
        self.method = method
        self.query = query
        self.params = params
        self.body = body
        self.headers = headers
        self._upload = upload          # (rfile, length, content type) on raw-body routes
        self.content_type = upload[2] if upload else None
        self.body_length = upload[1] if upload else None

    def if_match(self):
        v = (self.headers.get("If-Match") or "").strip()
        if v.startswith("W/"):
            v = v[2:]
        return v.strip('"') or None

    def _take(self):
        if not self._upload:
            raise ApiError(400, "bad_body", "This request carries no file, or it was already read.")
        rfile, n, _ = self._upload
        self._upload = None
        return rfile, n

    def save_body(self, path):
        """Stream the uploaded file to path and return its size. A body cut
        short leaves no file behind."""
        rfile, left = self._take()
        written = 0
        with open(path, "wb") as f:
            while left > 0:
                buf = rfile.read(min(CHUNK, left))
                if not buf:
                    break
                f.write(buf)
                written += len(buf)
                left -= len(buf)
        if left:
            with contextlib.suppress(OSError):
                os.unlink(path)
            raise ApiError(400, "bad_body", "The upload was cut short. Try again.")
        return written

    def read_body(self):
        rfile, n = self._take()
        data = rfile.read(n)
        if len(data) != n:
            raise ApiError(400, "bad_body", "The upload was cut short. Try again.")
        return data


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    timeout = 15                  # drop a connection that never sends a request
    server_version = "BGSCornerAdmin"
    sys_version = ""

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        self.dispatch("GET")

    def do_HEAD(self):
        self.dispatch("HEAD")

    def do_POST(self):
        self.dispatch("POST")

    def do_PUT(self):
        self.dispatch("PUT")

    def do_PATCH(self):
        self.dispatch("PATCH")

    def do_DELETE(self):
        self.dispatch("DELETE")

    def do_OPTIONS(self):
        self.dispatch("OPTIONS")

    def dispatch(self, method):
        app = self.server.app
        try:
            security.check_host(self, app.cfg)
            path = urllib.parse.urlsplit(self.path).path
            if app.admin_enabled and (path == "/admin" or path.startswith("/admin/")):
                return self.admin(method, path)
            if method not in ("GET", "HEAD"):
                raise ApiError(405, "method", "The store only serves pages.", headers={"Allow": "GET, HEAD"})
            static.serve_storefront(self, app.cfg, method)
        except ApiError as e:
            self.error(e, method)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            traceback.print_exc()
            self.error(ApiError(500, "internal", "Something went wrong in the admin. The server's terminal has the details."), method)

    # ---- admin -------------------------------------------------------------

    def admin(self, method, path):
        if path == "/admin":
            self.send_response(308)
            for k, v in ADMIN_HEADERS.items():
                self.send_header(k, v)
            self.send_header("Location", "/admin/")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if path == "/admin/":
            if method not in ("GET", "HEAD"):
                raise ApiError(405, "method", "Not allowed.", headers={"Allow": "GET, HEAD"})
            security.check_admin_page(self)
            return self.send_index(method)
        if path.startswith("/admin/ui/"):
            if method not in ("GET", "HEAD"):
                raise ApiError(405, "method", "Not allowed.", headers={"Allow": "GET, HEAD"})
            if not static.serve_ui(self, urllib.parse.unquote(path[len("/admin/ui/"):]), method):
                raise ApiError(404, "not_found", "Nothing here.")
            return
        if path.startswith("/admin/api/v1/"):
            return self.api(method, path[len("/admin/api/v1/"):])
        raise ApiError(404, "not_found", "Nothing here.")

    def send_index(self, method):
        page = (UI / "index.html").read_text(encoding="utf-8")
        data = page.replace("{{ADMIN_TOKEN}}", self.server.app.token).encode("utf-8")
        self.send_response(200)
        for k, v in ADMIN_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(data)

    def api(self, method, rest):
        app = self.server.app
        if method == "OPTIONS":
            # no preflight ever succeeds: there are no Access-Control headers
            raise ApiError(405, "method", "Not allowed.")
        security.check_api(self, app.cfg, app.token, method)
        route, params = routes.match(app.routes, method, rest)
        body, upload = None, None
        if route.body == "json":
            body = self.read_json(route.limit or LIMITS["json"])
        elif route.body == "raw":
            upload = self.check_upload(route)
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
        req = Request(app, method, {k: v[-1] for k, v in q.items()}, params, body, self.headers, upload)
        result = route.handler(req)
        if isinstance(result, routes.Raw):
            return self.send_raw(result, method)
        status, obj, extra = 200, result, {}
        if isinstance(result, tuple):
            status, obj = result[0], result[1]
            extra = result[2] if len(result) > 2 else {}
        self.send_json(status, obj, extra, method)

    def _length(self, what):
        if self.headers.get("Transfer-Encoding"):
            raise ApiError(411, "length_required", "Send the %s with a Content-Length." % what)
        n = (self.headers.get("Content-Length") or "").strip()
        if not n.isdigit():
            raise ApiError(411, "length_required", "Send the %s with a Content-Length." % what)
        return int(n)

    def read_json(self, limit):
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise ApiError(415, "unsupported_media_type", "Send the body as application/json.")
        n = self._length("body")
        if n > limit:
            raise ApiError(413, "too_large", "That is more than the admin accepts in one request.")
        raw = self.rfile.read(n)
        if len(raw) != n:
            raise ApiError(400, "bad_json", "The request body was cut short.")
        return strict_loads(raw)

    def check_upload(self, route):
        """A file sent as the body itself: its type and size are checked
        before a byte of it is read. Multipart and text bodies stop here."""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype not in route.types:
            raise ApiError(415, "unsupported_media_type", "This kind of file cannot be uploaded here.",
                           {"accepted": sorted(route.types)})
        n = self._length("file")
        if n == 0:
            raise ApiError(400, "bad_body", "The file is empty.")
        if n > route.limit:
            raise ApiError(413, "too_large", "That file is larger than the admin accepts here.", {"limit": route.limit})
        return (self.rfile, n, ctype)

    # ---- responses -----------------------------------------------------------

    def send_json(self, status, obj, extra, method):
        data = dumps(obj) if obj is not None else b""
        self.send_response(status)
        for k, v in ADMIN_HEADERS.items():
            self.send_header(k, v)
        for k, v in extra.items():
            self.send_header(k, v)
        if obj is not None:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if method != "HEAD" and data:
            self.wfile.write(data)

    def send_raw(self, r, method):
        self.send_response(r.status)
        for k, v in ADMIN_HEADERS.items():
            self.send_header(k, v)
        for k, v in r.headers.items():
            self.send_header(k, v)
        self.send_header("Content-Type", r.ctype)
        self.send_header("Content-Length", str(len(r.data)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(r.data)

    def error(self, e, method):
        if e.code == "bad_host":
            self.send_response(421)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_json(e.status, e.body(), e.headers, method)
