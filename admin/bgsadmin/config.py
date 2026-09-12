"""Paths, limits and the fixed lists everything else checks against.

Every path the admin touches is derived here from the repository it serves,
so a test can point the whole thing at a temporary clone with --repo. The
documents the admin edits are not listed here: each is a schema module
(schema.document_names()).
"""
import pathlib
import sys

ADMIN = pathlib.Path(__file__).resolve().parent.parent
UI = ADMIN / "ui"

# Request body caps, checked against Content-Length before anything is read.
# A route can set its own (Route(limit=...)); uploads always do.
LIMITS = {
    "json": 2 * 1024 * 1024,
}

# The pages build.py writes (plus 404.html, which it also writes). The
# storefront preview serves these and nothing else at the top level, which is
# what both deploys publish.
PAGES = ("index.html", "collection.html", "product.html", "gift-box.html", "cart.html",
         "checkout.html", "confirmed.html", "track-order.html", "account.html", "quiz.html",
         "corporate.html")

# Files under flow/assets that the deploys leave out: never served locally either.
UNPUBLISHED_ASSETS = {"assets/flow.css", "assets/cat/SOURCES.txt"}


class Config:
    """Everything that depends on which checkout is being served."""

    def __init__(self, repo, port=4310, storefront_only=False, no_push=False):
        self.repo = pathlib.Path(repo).resolve()
        self.flow = self.repo / "flow"
        self.content = self.flow / "content"
        self.backups = self.content / ".backups"
        self.assets = self.flow / "assets"
        self.port = int(port)
        self.storefront_only = bool(storefront_only)
        self.no_push = bool(no_push)
        self.python = sys.executable
        self.hosts = {"localhost:%d" % self.port, "127.0.0.1:%d" % self.port}
        self.origins = {"http://localhost:%d" % self.port, "http://127.0.0.1:%d" % self.port}

    def content_file(self, name):
        return self.content / ("%s.json" % name)

    def generated_files(self):
        """What build.py and make_derivatives.py write: snapshotted by every
        transaction so a failed build can put them back byte for byte."""
        out = [self.flow / p for p in PAGES]
        out += [self.flow / "404.html", self.flow / "robots.txt",
                self.assets / "catalogue.js", self.assets / "flow.min.css",
                self.flow / "tools" / "derivatives.json"]
        return out
