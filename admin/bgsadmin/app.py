"""The running admin: configuration, token, routes, store and build state."""
import secrets
import shutil

from . import routes
from .store.jsonstore import JSONStore


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.admin_enabled = not cfg.storefront_only
        # generated at start, held in memory only, never logged or written
        self.token = secrets.token_urlsafe(32) if self.admin_enabled else None
        self.routes = routes.load() if self.admin_enabled else []
        self.store = JSONStore(cfg) if self.admin_enabled else None
        self.build = {"ok": None, "at": None, "ms": None, "problems": []}
        self.probes = {}
        self.recovered = []

    def start(self):
        if not self.admin_enabled:
            return
        self.recovered = self.store.open()
        from . import media
        media.sweep(self.cfg)          # uploads left for more than a day
        try:
            import PIL
            pillow = PIL.__version__
        except ImportError:
            pillow = None
        path = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
        self.probes = {"pillow": pillow,
                       "ffmpeg": shutil.which("ffmpeg", path=path),
                       "ffprobe": shutil.which("ffprobe", path=path)}

    def note_build(self, build):
        """Remember the last build a save ran, for the build chip."""
        if build:
            import time
            self.build = {"ok": build.get("ok"), "at": time.time(), "ms": build.get("ms"),
                          "problems": build.get("problems", [])}
