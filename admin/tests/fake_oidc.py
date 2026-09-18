"""A stand-in for Auth0 in the storefront's sign-in tests: an OpenID Connect
provider on 127.0.0.1, standard library only, on a port of its own.

    idp = FakeOIDC(4793, client_id="...", callbacks=["http://localhost:4792/account.html"],
                   logouts=["http://localhost:4792/"], origins=["http://localhost:4792"])
    ...
    idp.close()

It answers as Auth0 does for a Single Page Application:

- GET /authorize checks response_type=code, the client id, the redirect_uri
  (exactly one of callbacks), a scope with openid, a state, a nonce and an
  S256 code_challenge. It signs the shopper in at once, with no form, and
  sends the browser back to redirect_uri with ?code and ?state. With .deny
  set it sends ?error=access_denied back instead; .wrong_state sends another
  state back and .wrong_nonce puts another nonce in the id_token.
- POST /oauth/token takes a form-encoded authorization_code grant: the code
  must be one it gave out, unused, for this client and redirect_uri, and the
  SHA-256 of code_verifier must be the code_challenge (PKCE). It answers with
  an id_token (iss, aud, sub, nonce, iat, exp, name, email, picture) and an
  access token, with Access-Control-Allow-Origin for an allowed origin only;
  an OPTIONS preflight is answered the same way.
- GET /v2/logout checks the client id and that returnTo is allowed, then
  redirects there.
- GET /userinfo answers the profile for an access token it gave out (the
  admin's own sign-in reads who someone is from here, as it does from Auth0).
  .email_verified False and .user say what it answers.
- GET /picture.png is the shopper's picture; /.well-known/openid-configuration
  lists the endpoints.

Anything it refuses gets a 400. Every request is recorded in .log as
(method, path, params, headers) and every answer to /authorize, /oauth/token
and /v2/logout in .events.
"""
import base64
import hashlib
import hmac
import http.server
import json
import os
import re
import struct
import threading
import time
import urllib.parse
import zlib

VERIFIER = re.compile(r"[A-Za-z0-9._~-]{43,128}")


def b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def png(rgb, size=8):
    """A small square PNG of one colour."""
    row = b"\x00" + bytes(rgb) * size
    body = zlib.compress(row * size)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", body) + chunk(b"IEND", b""))


class FakeOIDC:
    def __init__(self, port, client_id, callbacks, logouts, origins):
        self.port = int(port)
        self.base = "http://127.0.0.1:%d" % self.port
        self.client_id = client_id
        self.callbacks, self.logouts, self.origins = list(callbacks), list(logouts), list(origins)
        self.secret = os.urandom(32)
        self.user = {"sub": "auth0|fake-shopper-1", "name": "Noor Haddad", "email": "noor@example.com"}
        self.lifetime = 36000
        self.codes = {}
        self.tokens = {}                 # access token -> the profile /userinfo gives back
        self.log, self.events = [], []
        self.reset()
        idp = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                idp._handle(self, "GET")

            def do_POST(self):
                idp._handle(self, "POST")

            def do_OPTIONS(self):
                idp._handle(self, "OPTIONS")

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def reset(self):
        """Back to a plain sign-in, with nothing recorded."""
        self.deny = self.wrong_state = self.wrong_nonce = False
        self.email_verified = True
        del self.log[:]
        del self.events[:]

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def kinds(self):
        return [e["kind"] for e in self.events]

    # ---- the id_token ------------------------------------------------------------
    def id_token(self, nonce):
        now = int(time.time())
        claims = dict(self.user, iss=self.base + "/", aud=self.client_id, iat=now, exp=now + self.lifetime,
                      nonce=nonce, picture=self.base + "/picture.png", email_verified=True)
        head = b64url(json.dumps({"alg": "HS256", "typ": "JWT", "kid": "fake"}).encode())
        body = b64url(json.dumps(claims, ensure_ascii=False).encode("utf-8"))
        sig = b64url(hmac.new(self.secret, (head + "." + body).encode(), hashlib.sha256).digest())
        return head + "." + body + "." + sig

    # ---- answers -----------------------------------------------------------------
    def _send(self, h, status, body=b"", ctype="text/plain; charset=utf-8", headers=None):
        h.send_response(status)
        for k, v in (headers or {}).items():
            h.send_header(k, v)
        h.send_header("Content-Type", ctype)
        h.send_header("Content-Length", str(len(body)))
        h.send_header("Cache-Control", "no-store")
        h.end_headers()
        if h.command != "HEAD":
            h.wfile.write(body)

    def _refuse(self, h, kind, why, headers=None, as_json=False):
        self.events.append({"kind": kind, "ok": False, "why": why})
        if as_json:
            body = json.dumps({"error": "invalid_grant", "error_description": why}).encode()
            return self._send(h, 400, body, "application/json", headers)
        return self._send(h, 400, ("Refused: %s" % why).encode(), headers=headers)

    def _cors(self, h):
        origin = h.headers.get("Origin")
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"} if origin in self.origins else {"Vary": "Origin"}

    def _handle(self, h, method):
        url = urllib.parse.urlsplit(h.path)
        params = dict(urllib.parse.parse_qsl(url.query, keep_blank_values=True))
        body = b""
        if method == "POST":
            body = h.rfile.read(int(h.headers.get("Content-Length") or 0))
        self.log.append((method, url.path, params, dict(h.headers.items())))
        route = (method, url.path)
        if route == ("GET", "/authorize"):
            return self.authorize(h, params)
        if url.path == "/oauth/token" and method == "OPTIONS":
            return self._send(h, 204, headers=dict(self._cors(h), **{
                "Access-Control-Allow-Methods": "POST", "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Max-Age": "600"}))
        if route == ("POST", "/oauth/token"):
            return self.token(h, body)
        if route == ("GET", "/userinfo"):
            return self.userinfo(h)
        if route == ("GET", "/v2/logout"):
            return self.logout(h, params)
        if route == ("GET", "/picture.png"):
            return self._send(h, 200, png((168, 121, 30)), "image/png")
        if route == ("GET", "/.well-known/openid-configuration"):
            doc = {"issuer": self.base + "/", "authorization_endpoint": self.base + "/authorize",
                   "token_endpoint": self.base + "/oauth/token", "end_session_endpoint": self.base + "/v2/logout",
                   "response_types_supported": ["code"], "code_challenge_methods_supported": ["S256"],
                   "scopes_supported": ["openid", "profile", "email"]}
            return self._send(h, 200, json.dumps(doc).encode(), "application/json")
        return self._send(h, 404, b"Not found")

    def authorize(self, h, p):
        checks = (
            (p.get("response_type") == "code", "response_type must be code"),
            (p.get("client_id") == self.client_id, "unknown client_id"),
            (p.get("redirect_uri") in self.callbacks, "callback URL mismatch: %s" % p.get("redirect_uri")),
            ("openid" in (p.get("scope") or "").split(), "scope must include openid"),
            (bool(p.get("state")), "state missing"),
            (bool(p.get("nonce")), "nonce missing"),
            (p.get("code_challenge_method") == "S256", "code_challenge_method must be S256"),
            (re.fullmatch(r"[A-Za-z0-9_-]{43}", p.get("code_challenge") or "") is not None, "code_challenge must be a SHA-256 in base64url"),
        )
        for ok, why in checks:
            if not ok:
                return self._refuse(h, "authorize", why)
        back = {"state": "not-the-state-sent" if self.wrong_state else p["state"]}
        if self.deny:
            back.update(error="access_denied", error_description="The shopper said no")
            self.events.append({"kind": "authorize", "ok": True, "denied": True, "params": p})
        else:
            code = b64url(os.urandom(18))
            self.codes[code] = {"challenge": p["code_challenge"], "redirect_uri": p["redirect_uri"],
                                "nonce": "another-nonce" if self.wrong_nonce else p["nonce"]}
            back["code"] = code
            self.events.append({"kind": "authorize", "ok": True, "params": p, "code": code})
        return self._send(h, 302, headers={"Location": p["redirect_uri"] + "?" + urllib.parse.urlencode(back)})

    def token(self, h, raw):
        cors = self._cors(h)
        if not (h.headers.get("Content-Type") or "").startswith("application/x-www-form-urlencoded"):
            return self._refuse(h, "token", "the body must be form-encoded", cors, True)
        f = dict(urllib.parse.parse_qsl(raw.decode("utf-8"), keep_blank_values=True))
        grant = self.codes.pop(f.get("code"), None)
        verifier = f.get("code_verifier") or ""
        checks = (
            (f.get("grant_type") == "authorization_code", "grant_type must be authorization_code"),
            (f.get("client_id") == self.client_id, "unknown client_id"),
            (grant is not None, "unknown or used code"),
            (grant is not None and f.get("redirect_uri") == grant["redirect_uri"], "redirect_uri differs from the one sent to /authorize"),
            (VERIFIER.fullmatch(verifier) is not None, "code_verifier must be 43 to 128 unreserved characters"),
            (grant is not None and b64url(hashlib.sha256(verifier.encode()).digest()) == grant["challenge"],
             "code_verifier does not match the code_challenge"),
            ("client_secret" not in f, "a single page application sends no client secret"),
        )
        for ok, why in checks:
            if not ok:
                return self._refuse(h, "token", why, cors, True)
        self.events.append({"kind": "token", "ok": True, "origin": h.headers.get("Origin"),
                            "cookie": "Cookie" in h.headers})
        access = b64url(os.urandom(24))
        self.tokens[access] = dict(self.user, picture=self.base + "/picture.png",
                                   email_verified=self.email_verified)
        out = {"access_token": access, "id_token": self.id_token(grant["nonce"]),
               "token_type": "Bearer", "expires_in": 86400, "scope": "openid profile email"}
        return self._send(h, 200, json.dumps(out, ensure_ascii=False).encode("utf-8"), "application/json", cors)

    def userinfo(self, h):
        """Who the access token belongs to. Auth0 answers 401 for a token it
        did not give out, and so does this."""
        sent = (h.headers.get("Authorization") or "").split(" ", 1)
        token = sent[1] if len(sent) == 2 and sent[0].lower() == "bearer" else ""
        who = self.tokens.get(token)
        if not who:
            return self._send(h, 401, b'{"error":"invalid_token"}', "application/json")
        self.events.append({"kind": "userinfo", "ok": True, "email": who.get("email")})
        return self._send(h, 200, json.dumps(who, ensure_ascii=False).encode("utf-8"), "application/json")

    def logout(self, h, p):
        if p.get("client_id") != self.client_id:
            return self._refuse(h, "logout", "unknown client_id")
        if p.get("returnTo") not in self.logouts:
            return self._refuse(h, "logout", "returnTo is not an allowed logout URL: %s" % p.get("returnTo"))
        self.events.append({"kind": "logout", "ok": True, "params": p})
        return self._send(h, 302, headers={"Location": p["returnTo"]})


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Run the fake sign-in provider on its own.")
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--client-id", required=True)
    ap.add_argument("--site", required=True, help="the storefront's origin, like http://localhost:5100")
    a = ap.parse_args()
    idp = FakeOIDC(a.port, a.client_id, [a.site + "/account.html"], [a.site + "/"], [a.site])
    print("fake provider at", idp.base)
    try:
        idp.thread.join()
    except KeyboardInterrupt:
        idp.close()
