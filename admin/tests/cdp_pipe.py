"""Headless Chrome driven over --remote-debugging-pipe with the standard
library only, for tests that type, press keys, paste and click in an admin
screen and read the page back. Key presses go through Chrome's own input
pipeline, so a screen's key handlers and default actions (Tab moving focus)
run as they would for a person.

    c = Chrome()
    c.go("http://localhost:4773/admin/#/bulk")
    c.wait("document.querySelector('[role=grid]')")
    c.key("ArrowDown"); c.type("90"); c.key("Enter")
    c.close()
"""
import fcntl
import json
import os
import pathlib
import select
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "devtools"))
from dom_diff import CHROME  # noqa: E402

KEYS = {
    "Enter": (13, "\r"), "Tab": (9, None), "Escape": (27, None), "F2": (113, None),
    "ArrowUp": (38, None), "ArrowDown": (40, None), "ArrowLeft": (37, None), "ArrowRight": (39, None),
    "Backspace": (8, None), "Delete": (46, None), "Home": (36, None), "End": (35, None),
}
MODS = {"alt": 1, "ctrl": 2, "meta": 4, "shift": 8}


class Chrome:
    def __init__(self, width=1280, height=900, args=()):
        """args: more Chrome switches, such as --host-resolver-rules to keep
        a test off the network."""
        self.prof = tempfile.mkdtemp(prefix="cdp-prof-")
        self.downloads = tempfile.mkdtemp(prefix="cdp-dl-")
        r_cmd, self.w = os.pipe()
        self.r, w_resp = os.pipe()
        # Chrome reads commands on fd 3 and answers on fd 4. The child's ends
        # go to high numbers first, so moving them there cannot overwrite
        # one with the other.
        hi_r = fcntl.fcntl(r_cmd, fcntl.F_DUPFD, 20)
        hi_w = fcntl.fcntl(w_resp, fcntl.F_DUPFD, 20)

        def child():
            os.dup2(hi_r, 3)
            os.dup2(hi_w, 4)

        self.p = subprocess.Popen(
            [CHROME, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
             "--disable-extensions", "--disable-background-networking", "--disable-sync", "--mute-audio",
             "--hide-scrollbars", "--user-data-dir=" + self.prof, "--window-size=%d,%d" % (width, height),
             "--remote-debugging-pipe"] + list(args) + ["about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, preexec_fn=child, close_fds=False)
        for fd in (r_cmd, w_resp, hi_r, hi_w):
            os.close(fd)
        self.buf, self.n, self.events, self.sid = b"", 0, [], None
        tid = self.call("Target.createTarget", {"url": "about:blank"}, browser=True)["targetId"]
        self.sid = self.call("Target.attachToTarget", {"targetId": tid, "flatten": True}, browser=True)["sessionId"]
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.size(width, height)
        self.call("Browser.setDownloadBehavior", {"behavior": "allow", "downloadPath": self.downloads}, browser=True)

    def size(self, width, height=900):
        self.call("Emulation.setDeviceMetricsOverride", {"width": width, "height": height, "deviceScaleFactor": 1, "mobile": False})

    def _read(self, timeout):
        end = time.monotonic() + timeout
        while b"\0" not in self.buf:
            left = end - time.monotonic()
            if left <= 0:
                raise TimeoutError("Chrome did not answer")
            if select.select([self.r], [], [], left)[0]:
                chunk = os.read(self.r, 1 << 20)
                if not chunk:
                    raise RuntimeError("Chrome closed the pipe")
                self.buf += chunk
        msg, self.buf = self.buf.split(b"\0", 1)
        return json.loads(msg)

    def call(self, method, params=None, browser=False, timeout=30):
        self.n += 1
        msg = {"id": self.n, "method": method, "params": params or {}}
        if not browser and self.sid:
            msg["sessionId"] = self.sid
        os.write(self.w, json.dumps(msg).encode() + b"\0")
        while True:
            m = self._read(timeout)
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError("%s: %s" % (method, m["error"]))
                return m.get("result", {})
            self.events.append(m)

    def js(self, expr):
        # userGesture: a click from here counts as a person's, so Chrome does
        # not hold back a second download or a dialog.
        r = self.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True, "userGesture": True})
        if r.get("exceptionDetails"):
            raise RuntimeError("script failed: %s" % json.dumps(r["exceptionDetails"])[:600])
        return r.get("result", {}).get("value")

    def wait(self, expr, timeout=20, what=None):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.js(expr):
                return True
            time.sleep(0.1)
        raise AssertionError("timed out waiting for %s" % (what or expr))

    def go(self, url):
        self.call("Page.navigate", {"url": url})

    def key(self, name, mods=()):
        m = sum(MODS[x] for x in mods)
        if name in KEYS:
            (vk, text), key, code = KEYS[name], name, name
        else:
            key, text = name, (None if m & (MODS["ctrl"] | MODS["meta"]) else name)
            vk = ord(name.upper()) if name.isalnum() else 0
            code = "Key" + name.upper() if name.isalpha() else "Digit" + name if name.isdigit() else ""
        ev = {"key": key, "code": code, "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk, "modifiers": m}
        down = dict(ev, type="keyDown" if text else "rawKeyDown")
        if text:
            down.update(text=text, unmodifiedText=text)
        self.call("Input.dispatchKeyEvent", down)
        self.call("Input.dispatchKeyEvent", dict(ev, type="keyUp"))

    def type(self, s):
        for ch in s:
            self.key(ch)

    def errors(self):
        """Uncaught exceptions and console errors the page produced."""
        out = []
        for e in self.events:
            if e.get("method") == "Runtime.exceptionThrown":
                out.append(json.dumps(e["params"]["exceptionDetails"])[:400])
            elif e.get("method") == "Runtime.consoleAPICalled" and e["params"].get("type") == "error":
                out.append(json.dumps(e["params"]["args"])[:400])
        return out

    def close(self):
        try:
            self.p.kill()
            self.p.wait(5)
        finally:
            for fd in (self.r, self.w):
                try:
                    os.close(fd)
                except OSError:
                    pass
            shutil.rmtree(self.prof, ignore_errors=True)
            shutil.rmtree(self.downloads, ignore_errors=True)
