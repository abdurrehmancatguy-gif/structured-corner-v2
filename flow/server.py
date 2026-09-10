"""Static server for the BGS Corner front end.

Sends no-store on every response. The default http.server sends Last-Modified,
which let browsers keep serving stale HTML after a rebuild - several rounds of
"the change didn't apply" traced back to exactly that.
"""
import functools, http.server, socketserver, os, sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 4310

class NoCache(http.server.SimpleHTTPRequestHandler):
    timeout = 15  # drop a connection that never sends a request
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()
    def log_message(self, fmt, *args):
        pass

os.chdir(os.path.dirname(os.path.abspath(__file__)))
class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """One thread per connection. Single-threaded, one idle connection (a
    browser's speculative preconnect sends nothing) blocked every request
    queued behind it, and pages timed out."""
    allow_reuse_address = True
    daemon_threads = True

    def handle_error(self, request, client_address):
        # a browser leaving mid-download is not an error worth a traceback
        if not isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            super().handle_error(request, client_address)

with Server(("", PORT), NoCache) as httpd:
    print("serving %s on http://localhost:%d" % (os.getcwd(), PORT))
    httpd.serve_forever()
