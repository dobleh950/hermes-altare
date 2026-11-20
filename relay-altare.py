#!/usr/bin/env python3
"""Altare relay: Hermes -> http://127.0.0.1:8787/v1 -> https://api.cent-ai.dev/v1

Adapted from ~/workspace/hermes-install/relay.py for deployment on
Altare (or any plain container host) where there is NO Secure Vault.

Difference from the VM relay: the Cent AI API key comes from the
CENTAI_API_KEY environment variable, read once at startup. The key is
never written to a file or a log; it is only attached server-side as
the Authorization header on outbound requests to api.cent-ai.dev.
The relay binds 127.0.0.1:8787 ONLY, so it is never reachable from
outside the container — the key cannot leak through the relay port.

Endpoints forwarded: GET /v1/models, POST /v1/chat/completions (both
streaming SSE and plain JSON). Responses are streamed chunk-by-chunk
to the client, never buffered whole. Cent AI's base is /v1, so BASE
is https://api.cent-ai.dev and the incoming /v1/* path is appended
as-is.

Required env: CENTAI_API_KEY (set in Altare as an app env var/secret).
Model served through this relay: hy4-flash:free (Cent AI free variant,
$0.00/token). See config.yaml (model.default).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CENTAI_API_KEY = os.environ.get("CENTAI_API_KEY", "")
if not CENTAI_API_KEY:
    sys.stderr.write("[relay-altare] FATAL: CENTAI_API_KEY env var is not set\n")
    sys.stderr.flush()
    sys.exit(1)

HOST = "api.cent-ai.dev"
BASE = f"https://{HOST}"
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = 8787
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # keep the log clean, no bodies/keys
        sys.stderr.write("[relay] %s - %s\n" % (self.address_string(), fmt % args))
        sys.stderr.flush()

    def _forward(self, method):
        path = self.path
        if not path.startswith("/v1/"):
            self._send_json(404, {"error": {"message": "relay only serves /v1/*", "type": "not_found"}})
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None
        req = urllib.request.Request(BASE + path, method=method)
        req.add_header("User-Agent", UA)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        # Key from env only; attached server-side, never logged or stored.
        req.add_header("Authorization", f"Bearer {CENTAI_API_KEY}")
        try:
            with urllib.request.build_opener(NoRedirect()).open(
                req, data=body, timeout=300
            ) as resp:
                self._stream(resp)
        except urllib.error.HTTPError as exc:
            self._stream(exc)
        except Exception as exc:  # noqa: BLE001 - report upstream failure as 502
            self._send_json(502, {"error": {"message": f"relay upstream error: {exc}", "type": "relay_error"}})

    def _stream(self, resp):
        status = getattr(resp, "status", 200)
        ctype = resp.headers.get("Content-Type", "application/json")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        while True:
            chunk = resp.read(8192)
            if not chunk:
                break
            self.wfile.write(b"%x\r\n%s\r\n" % (len(chunk), chunk))
            self.wfile.flush()
        self.wfile.write(b"0\r\n\r\n")
        self.wfile.flush()

    def _send_json(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def do_GET(self):
        self._forward("GET")

    def do_POST(self):
        self._forward("POST")


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), Handler)
    sys.stderr.write(f"[relay] listening on http://{LISTEN_HOST}:{LISTEN_PORT}/v1 -> {BASE}\n")
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
