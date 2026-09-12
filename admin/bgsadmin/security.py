"""Who may talk to the admin, and which files a request may name.

The admin has no login yet and listens only on 127.0.0.1, so the threats are
web pages open in the owner's own browser: a page that rebinds a hostname to
127.0.0.1 (stopped by the Host check), a page that posts to localhost
(stopped by the Origin and Fetch Metadata checks, JSON-only bodies and the
per-run token), and script on the storefront preview, which shares this
origin (stopped by serving the admin page only to top-level navigations,
COOP, and a storefront CSP that forbids network calls). See
docs/PLAN.md, security_model.
"""
import hmac
import os
import pathlib
import stat

from .errors import ApiError

ADMIN_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; "
             "media-src 'self' blob:; connect-src 'self'; frame-src 'self'; font-src 'self'; "
             "form-action 'none'; base-uri 'none'; frame-ancestors 'none'")

ADMIN_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": ADMIN_CSP,
}

# The storefront preview keeps flow/server.py's no-store headers, so a rebuild
# shows on reload. shop.js makes no network calls, so connect-src 'none' costs
# nothing and means a script on a store page could not drive the API even if
# it somehow held the token.
STOREFRONT_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "connect-src 'none'",
}

SAFE_METHODS = ("GET", "HEAD")


def check_host(handler, cfg):
    host = (handler.headers.get("Host") or "").strip().lower()
    if host not in cfg.hosts:
        raise ApiError(421, "bad_host", "Wrong host.")


def check_admin_page(handler):
    """The admin HTML carries the token, so only a real top-level visit gets
    it: not fetch(), not an iframe, not a navigation started by another site."""
    h = handler.headers
    mode, dest, site = h.get("Sec-Fetch-Mode"), h.get("Sec-Fetch-Dest"), h.get("Sec-Fetch-Site")
    if mode is not None and mode != "navigate":
        raise ApiError(403, "not_navigation", "Open the admin by typing its address.")
    if dest is not None and dest != "document":
        raise ApiError(403, "not_navigation", "The admin cannot be shown inside another page.")
    if site is not None and site not in ("none", "same-origin"):
        raise ApiError(403, "not_navigation", "Open the admin by typing its address, not from a link on another site.")


def check_api(handler, cfg, token, method):
    """Every API call carries the token; every change also carries our Origin."""
    sent = handler.headers.get("X-Admin-Token") or ""
    if not token or not hmac.compare_digest(sent.encode(), token.encode()):
        raise ApiError(401, "bad_token", "The admin restarted or this page is stale: reload it.")
    site = handler.headers.get("Sec-Fetch-Site")
    if site is not None and site != "same-origin":
        raise ApiError(403, "forbidden_origin", "Requests must come from the admin itself.")
    if method not in SAFE_METHODS:
        origin = handler.headers.get("Origin")
        if not origin or origin == "null" or origin not in cfg.origins:
            raise ApiError(403, "forbidden_origin", "Requests must come from the admin itself.")


def safe_join(root, rel, must_exist=True):
    """Resolve rel under root, or return None.

    Refused: empty, absolute, backslashes, NUL, '.' or '..' segments, any
    segment starting with a dot (no .backups, no .git), a symlink on any
    component, and anything that resolves outside root."""
    if not isinstance(rel, str) or not rel or "\x00" in rel or "\\" in rel or rel.startswith("/"):
        return None
    parts = rel.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        return None
    root = pathlib.Path(root).resolve()
    cur = root
    for i, p in enumerate(parts):
        cur = cur / p
        try:
            st = os.lstat(cur)
        except FileNotFoundError:
            if must_exist or i != len(parts) - 1:
                return None
            break
        if stat.S_ISLNK(st.st_mode):
            return None
    real = os.path.realpath(cur)
    if not real.startswith(str(root) + os.sep):
        return None
    return cur
