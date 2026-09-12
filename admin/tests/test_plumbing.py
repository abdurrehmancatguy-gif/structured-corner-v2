"""The server plumbing other areas build on: raw-body uploads, non-JSON
responses and background jobs. Runs a bare server with two routes of its own
on port 4732, against no repository content at all."""
import http.client
import json
import os
import pathlib
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from bgsadmin import jobs  # noqa: E402
from bgsadmin.config import Config  # noqa: E402
from bgsadmin.errors import ApiError  # noqa: E402
from bgsadmin.httpd import Handler, Server  # noqa: E402
from bgsadmin.routes import Raw, Route  # noqa: E402

PORT = int(os.environ.get("ADMIN_PLUMBING_PORT", "4732"))


def upload(req):
    fd, path = tempfile.mkstemp()
    os.close(fd)
    n = req.save_body(path)
    data = pathlib.Path(path).read_bytes()
    os.unlink(path)
    return {"type": req.content_type, "bytes": n, "head": data[:4].decode("latin-1")}


def download(req):
    return Raw(b"\xef\xbb\xbfid,name\r\nvibe,Vibe\r\n", "text/csv; charset=utf-8",
               {"Content-Disposition": 'attachment; filename="products.csv"'})


class FakeApp:
    admin_enabled = True

    def __init__(self):
        self.cfg = Config(tempfile.gettempdir(), port=PORT)
        self.token = "test-token"
        self.routes = [Route("POST", r"up", upload, body="raw", types={"image/png"}, limit=64),
                       Route("GET", r"down", download)]


class PlumbingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = Server(("127.0.0.1", PORT), Handler, FakeApp())
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        h = {"Host": "localhost:%d" % PORT, "X-Admin-Token": "test-token", "Origin": "http://localhost:%d" % PORT}
        h.update(headers or {})
        c.request(method, "/admin/api/v1/" + path, body=body, headers=h)
        r = c.getresponse()
        out = r.status, dict(r.getheaders()), r.read()
        c.close()
        return out

    def test_raw_upload_is_typed_sized_and_streamed(self):
        st, _, body = self.req("POST", "up", b"\x89PNG0123", {"Content-Type": "image/png"})
        self.assertEqual(st, 200, body)
        got = json.loads(body)
        self.assertEqual((got["type"], got["bytes"], got["head"]), ("image/png", 8, "\x89PNG"))
        self.assertEqual(self.req("POST", "up", b"abc", {"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.req("POST", "up", b"x" * 65, {"Content-Type": "image/png"})[0], 413)
        self.assertEqual(self.req("POST", "up", b"", {"Content-Type": "image/png"})[0], 400)

    def test_raw_response_keeps_the_security_headers(self):
        st, hd, body = self.req("GET", "down")
        self.assertEqual(st, 200)
        self.assertTrue(body.startswith(b"\xef\xbb\xbfid,name"))
        self.assertEqual(hd.get("Content-Type"), "text/csv; charset=utf-8")
        self.assertIn("products.csv", hd.get("Content-Disposition", ""))
        self.assertEqual(hd.get("Cache-Control"), "no-store")
        self.assertIn("frame-ancestors 'none'", hd.get("Content-Security-Policy", ""))

    def test_a_raw_route_must_declare_types_and_a_limit(self):
        with self.assertRaises(ValueError):
            Route("POST", r"x", upload, body="raw")

    def test_jobs_report_results_and_failures(self):
        ok = jobs.start("test", lambda log: (log("working"), {"n": 1})[1])
        bad = jobs.start("test", lambda log: (_ for _ in ()).throw(ApiError(422, "nope", "It did not work.")))
        for _ in range(50):
            if ok.finished and bad.finished:
                break
            time.sleep(0.05)
        self.assertEqual(ok.view()["state"], "done")
        self.assertEqual(ok.view()["result"], {"n": 1})
        self.assertEqual(ok.view()["log_tail"], ["working"])
        self.assertEqual(bad.view()["state"], "failed")
        self.assertEqual(bad.view()["error"]["code"], "nope")
        self.assertIs(jobs.get(ok.id), ok)


if __name__ == "__main__":
    unittest.main()
