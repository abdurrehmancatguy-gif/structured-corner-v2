"""Files: the storefront preview and the admin's own UI.

The preview serves exactly what the deploys publish (flow/*.html,
favicon.ico, robots.txt and flow/assets/ less the stylesheet source and
SOURCES.txt), so a page that works here cannot 404 live because it leaned on
content/, tools/ or flow.css. A miss gets the site's own 404.html, as on
Netlify and GitHub Pages.
"""
import re
import urllib.parse

from .config import UI, UNPUBLISHED_ASSETS
from .security import ADMIN_HEADERS, safe_join, storefront_headers

MIME = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".txt": "text/plain; charset=utf-8", ".png": "image/png", ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon", ".mp4": "video/mp4",
    ".woff2": "font/woff2",
}
UI_TYPES = {".js", ".css", ".png", ".ico"}
CHUNK = 64 * 1024


def published(rel):
    if rel in ("favicon.ico", "robots.txt"):
        return True
    if "/" not in rel:
        return rel.endswith(".html")
    return rel.startswith("assets/") and rel not in UNPUBLISHED_ASSETS


def _range(header, size):
    """One byte range, or None for the whole file, or 'bad' for a 416.
    Safari will not play an mp4 from a server without it."""
    if not header:
        return None
    m = re.fullmatch(r"\s*bytes=(\d*)-(\d*)\s*", header)
    if not m or (m.group(1) == "" and m.group(2) == ""):
        return None
    a, b = m.group(1), m.group(2)
    if a == "":
        n = int(b)
        if n == 0:
            return "bad"
        start, end = max(0, size - n), size - 1
    else:
        start = int(a)
        end = min(int(b), size - 1) if b else size - 1
    if start >= size or start > end:
        return "bad"
    return start, end


def send_file(handler, path, method, headers, status=200, allow_range=False):
    size = path.stat().st_size
    ctype = MIME.get(path.suffix.lower(), "application/octet-stream")
    rng = _range(handler.headers.get("Range"), size) if allow_range else None
    if rng == "bad":
        handler.send_response(416)
        for k, v in headers.items():
            handler.send_header(k, v)
        handler.send_header("Content-Range", "bytes */%d" % size)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    start, end = rng if rng else (0, size - 1)
    handler.send_response(206 if rng else status)
    for k, v in headers.items():
        handler.send_header(k, v)
    handler.send_header("Content-Type", ctype)
    if allow_range:
        handler.send_header("Accept-Ranges", "bytes")
    if rng:
        handler.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
    handler.send_header("Content-Length", str(max(0, end - start + 1)))
    handler.end_headers()
    if method == "HEAD" or size == 0:
        return
    with open(path, "rb") as f:
        f.seek(start)
        left = end - start + 1
        while left > 0:
            buf = f.read(min(CHUNK, left))
            if not buf:
                break
            handler.wfile.write(buf)
            left -= len(buf)


def send_404(handler, cfg, method):
    page = cfg.flow / "404.html"
    if page.is_file():
        return send_file(handler, page, method, storefront_headers(cfg), status=404)
    handler.send_response(404)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def serve_storefront(handler, cfg, method):
    path = urllib.parse.urlsplit(handler.path).path
    rel = urllib.parse.unquote(path).lstrip("/") or "index.html"
    target = safe_join(cfg.flow, rel) if published(rel) else None
    if target is None or not target.is_file():
        return send_404(handler, cfg, method)
    send_file(handler, target, method, storefront_headers(cfg), allow_range=True)


def ui_file(rel):
    """A file of the admin UI, from an allow-list of types under admin/ui."""
    if "." not in rel or rel[rel.rindex("."):].lower() not in UI_TYPES:
        return None
    target = safe_join(UI, rel)
    return target if target is not None and target.is_file() else None


def serve_ui(handler, rel, method):
    target = ui_file(rel)
    if target is None:
        return False
    send_file(handler, target, method, ADMIN_HEADERS)
    return True
