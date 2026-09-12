#!/usr/bin/env python3
"""The BGS Corner local server: the storefront preview and the admin.

    python3 admin/server.py              # http://localhost:4310/ and http://localhost:4310/admin/
    python3 admin/server.py --port 4701 --repo /tmp/clone --no-push

It listens on 127.0.0.1 only: the admin has no login yet, so it must never be
reachable from another machine. See DESIGN.md.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bgsadmin import config, httpd              # noqa: E402
from bgsadmin.app import App                    # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="BGS Corner storefront preview and admin (local only).")
    ap.add_argument("port_pos", nargs="?", type=int, help=argparse.SUPPRESS)   # flow/server.py passed the port bare
    ap.add_argument("--port", type=int)
    ap.add_argument("--repo", help="serve and edit this checkout instead of the one the admin lives in")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--storefront-only", action="store_true", help="the preview alone: no admin, no token")
    ap.add_argument("--no-push", action="store_true", help="refuse to publish to GitHub (for tests)")
    args = ap.parse_args()

    if args.host not in ("127.0.0.1", "localhost"):
        sys.exit("The admin only listens on 127.0.0.1: it has no login yet.")
    port = args.port or args.port_pos or 4310
    repo = pathlib.Path(args.repo).resolve() if args.repo else config.ADMIN.parent
    cfg = config.Config(repo, port, args.storefront_only, args.no_push)
    if (cfg.flow / "admin").exists():
        sys.exit("flow/admin exists. flow/ is published, so nothing of the admin may live there.")
    if not cfg.content.is_dir():
        sys.exit("No flow/content in %s." % repo)

    app = App(cfg)
    app.start()
    try:
        srv = httpd.Server(("127.0.0.1", port), httpd.Handler, app)
    except OSError as e:
        sys.exit("Port %d is not free (%s)." % (port, e.strerror))
    print("storefront  http://localhost:%d/" % port)
    if app.admin_enabled:
        print("admin       http://localhost:%d/admin/" % port)
    if app.recovered:
        print("rolled back an interrupted save: %s" % ", ".join(app.recovered))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
