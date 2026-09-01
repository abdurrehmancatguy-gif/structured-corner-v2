"""Static server for the BGS Corner front end.

Sends no-store on every response. The default http.server sends Last-Modified,
which let browsers keep serving stale HTML after a rebuild — several rounds of
"the change didn't apply" traced back to exactly that.
"""
import functools, http.server, socketserver, os, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4310

class NoCache(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()
    def log_message(self, fmt, *args):
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))
socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", PORT), NoCache) as httpd:
    print("serving %s on http://localhost:%d" % (os.getcwd(), PORT))
    httpd.serve_forever()
