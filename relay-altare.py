#!/usr/bin/env python3
"""Altare relay: Hermes -> http://127.0.0.1:8787/v1 -> samp.team or Cent AI.

Upstream is chosen by env var (samp.team wins when set):
- SAMP_API_KEY set -> https://api.samp.team (model gemini-4-argon).
- else CENTAI_API_KEY set -> https://api.cent-ai.dev (deepseek-v4.1-flash:free, $0).

The relay rewrites the requested `model` in chat-completion bodies to the
model that belongs to the chosen upstream (see UPSTREAM_MODEL below), so
Hermes keeps working whichever key is set: with the samp.team key present
the bot talks to samp.team, without it it falls back to Cent AI instead
of sending an unknown model name to the wrong upstream and breaking.

The key comes from the environment, read once at startup. It is never
written to a file or a log; it is only attached server-side as the
Authorization header on outbound requests. The relay binds 127.0.0.1:8787
ONLY, so it is never reachable from outside the container.

Endpoints forwarded: GET /v1/models, POST /v1/chat/completions (both
streaming SSE and plain JSON). Responses are streamed chunk-by-chunk
to the client, never buffered whole.

Required env: SAMP_API_KEY or CENTAI_API_KEY (set in Altare as
an app env var/secret).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

CENTAI_API_KEY = os.environ.get("CENTAI_API_KEY", "")
SAMP_API_KEY = os.environ.get("SAMP_API_KEY", "")
if SAMP_API_KEY:
    HOST = "api.samp.team"
    API_KEY = SAMP_API_KEY
elif CENTAI_API_KEY:
    HOST = "api.cent-ai.dev"
    API_KEY = CENTAI_API_KEY
else:
    sys.stderr.write("[relay-altare] FATAL: set SAMP_API_KEY or CENTAI_API_KEY env var\n")
    sys.stderr.flush()
    sys.exit(1)

# Both upstreams serve their OpenAI-compatible API under /v1, so the
# base is just the host; the relay appends the /v1/* path as-is.
BASE = f"https://{HOST}"
UPSTREAM_MODEL = (
    "gemini-4-argon"
    if HOST == "api.samp.team"
    else "deepseek-v4.1-flash:free"
)
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
        if body:
            # Rewrite the requested model to the one this upstream serves;
            # anything unparseable is forwarded untouched.
            try:
                payload = json.loads(body)
            except ValueError:
                payload = None
            if isinstance(payload, dict) and "model" in payload:
                payload["model"] = UPSTREAM_MODEL
                body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(BASE + path, method=method)
        req.add_header("User-Agent", UA)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        # Key from env only; attached server-side, never logged or stored.
        req.add_header("Authorization", f"Bearer {API_KEY}")
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
