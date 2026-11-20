#!/usr/bin/env python3
"""Tiny health server for the Altare app port.

Altare routes TCP traffic to the app on $PORT. This server answers
200 on /health and 404 on everything else. It serves nothing else and
does NOT proxy to the relay (the relay binds 127.0.0.1:8787 and must
never be publicly reachable — it attaches the paid Cent AI key).
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "8080"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[health] %s - %s\n" % (self.address_string(), fmt % args))
        sys.stderr.flush()

    def _send_json(self, status, obj):
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()

    def do_GET(self):
        if self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "not found"})


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    sys.stderr.write(f"[health] listening on 0.0.0.0:{PORT} (/health)\n")
    sys.stderr.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
