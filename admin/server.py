#!/usr/bin/env python3
"""The BGS Corner local server: the storefront preview and the admin.

    python3 admin/server.py              # http://localhost:4310/ and http://localhost:4310/admin/
    python3 admin/server.py --port 4701 --repo /tmp/clone --no-push
    admin/.venv/bin/python admin/server.py --store postgres --dsn "host=/tmp port=5432 dbname=bgs_corner user=bgs_corner_app"

Which store holds the content: --store and --dsn, then this checkout's own
admin/local/store.json (dbtool migrate --apply writes it), then the JSON
files. In PostgreSQL mode the admin never falls back to the files: it does not
start when the database is not answering (exit status 3), and refuses (2) a
database that is not this checkout's or not up to date.

It listens on 127.0.0.1 only: the admin has no login yet, so it must never be
reachable from another machine. See DESIGN.md.
"""
import argparse
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bgsadmin import adminauth, config, httpd   # noqa: E402
from bgsadmin.app import App                    # noqa: E402
from bgsadmin.store.base import CannotStart     # noqa: E402


def stop(message, status):
    sys.stderr.write(message + "\n")
    sys.stderr.flush()
    sys.exit(status)


def main():
    ap = argparse.ArgumentParser(description="BGS Corner storefront preview and admin (local only).")
    ap.add_argument("port_pos", nargs="?", type=int, help=argparse.SUPPRESS)   # flow/server.py passed the port bare
    ap.add_argument("--port", type=int)
    ap.add_argument("--repo", help="serve and edit this checkout instead of the one the admin lives in")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--storefront-only", action="store_true", help="the preview alone: no admin, no token")
    ap.add_argument("--no-push", action="store_true", help="refuse to publish to GitHub (for tests)")
    ap.add_argument("--store", choices=config.STORES,
                    help="json: the files in flow/content; postgres: the database. Without it, "
                         "admin/local/store.json chooses, else json")
    ap.add_argument("--dsn", help='the database for --store postgres: "host=<socket folder> port=... dbname=... '
                                  'user=...", never a password')
    args = ap.parse_args()

    # Off this machine the admin needs its own login (adminauth): App refuses
    # to start without one, so a wider address can never be the open admin.
    port = args.port or args.port_pos or 4310
    repo = pathlib.Path(args.repo).resolve() if args.repo else config.ADMIN.parent
    store, dsn = "json", None
    if not args.storefront_only:
        try:
            store, dsn = config.choose_store(repo, args.store, args.dsn)
        except ValueError as e:
            stop(str(e), 2)
    try:
        auth = adminauth.settings(repo)
    except CannotStart as e:
        sys.exit(e.message if hasattr(e, "message") else str(e))
    cfg = config.Config(repo, port, args.storefront_only, args.no_push, store=store, dsn=dsn,
                        host=args.host, base_url=auth.base_url if auth else None)
    if (cfg.flow / "admin").exists():
        sys.exit("flow/admin exists. flow/ is published, so nothing of the admin may live there.")
    if not cfg.content.is_dir():
        sys.exit("No flow/content in %s." % repo)

    try:
        app = App(cfg)
        app.start()
    except CannotStart as e:
        stop(e.message + (" The admin did not start; nothing was changed." if e.status == 3 else ""), e.status)
    try:
        srv = httpd.Server((args.host, port), httpd.Handler, app)
    except OSError as e:
        if app.store is not None:
            app.store.close()
        sys.exit("Port %d is not free (%s)." % (port, e.strerror))
    print("storefront  http://localhost:%d/" % port)
    if app.admin_enabled:
        print("admin       http://localhost:%d/admin/" % port)
        if app.auth:
            print("sign-in     %s, %d %s allowed%s" % (app.auth.domain, len(app.auth.allowed),
                                                       "person" if len(app.auth.allowed) == 1 else "people",
                                                       "" if app.auth_required else " (not asked for on this machine)"))
        print("store       %s" % app.store.describe())
        for w in app.store.warnings():
            print("warning     %s" % w)
    kept = set(app.store.kept) if app.store is not None else set()
    back = [n for n in app.recovered if n not in kept]
    if back:
        print("rolled back an interrupted save: %s" % ", ".join(back))
    if kept:
        print("finished an interrupted save the database had kept: %s" % ", ".join(n for n in app.recovered if n in kept))
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        if app.store is not None:
            app.store.close()


if __name__ == "__main__":
    main()
