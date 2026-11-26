#!/usr/bin/env python3
"""Altare relay: Hermes -> http://127.0.0.1:8787/v1 -> CanTrustAI or Cent AI.


Upstream is CanTrustAI, model anthropic/claude-haiku-5.5, with Cent AI
(hy4-flash:free) as fallback. The samp.team lane was REMOVED 2026-11-24 on Bos's
order ("ubah ke hy4 aja", no paid models): with the samp.team key
present the relay used to prefer samp.team, whose models all return
400 unavailable, and Astra is paid. The previous Cent AI fallback
model (deepseek-v4.1-flash:free) no longer exists (404), which is
why the bot could not answer at all.


The relay rewrites the requested `model` in chat-completion bodies
to anthropic/claude-haiku-5.5 for CanTrustAI or hy4-flash:free for the Cent AI fallback (see UPSTREAM_MODEL below), so Hermes keeps
working whichever model name its config carries.


The key comes from the environment, read once at startup. It is never
written to a file or a log; it is only attached server-side as the
Authorization header on outbound requests. The relay binds 127.0.0.1:8787
ONLY, so it is never reachable from outside the container.


Endpoints forwarded: GET /v1/models, POST /v1/chat/completions (both
streaming SSE and plain JSON). Responses are streamed chunk-by-chunk
to the client, never buffered whole.


Required env: CANTRUST_API_KEY or CENTAI_API_KEY (set in Altare as an app env var/secret).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


CANTRUST_API_KEY = os.environ.get("CANTRUST_API_KEY", "")
CENTAI_API_KEY = os.environ.get("CENTAI_API_KEY", "")
if CANTRUST_API_KEY:
    HOST = "api.cantrustai.xyz"
    API_KEY = CANTRUST_API_KEY
    UPSTREAM_MODEL = "anthropic/claude-haiku-5.5"
elif CENTAI_API_KEY:
    HOST = "api.cent-ai.dev"
    API_KEY = CENTAI_API_KEY
    UPSTREAM_MODEL = "hy4-flash:free"
else:
    sys.stderr.write("[relay-altare] FATAL: set CANTRUST_API_KEY or CENTAI_API_KEY env var\n")
    sys.stderr.flush()
    sys.exit(1)


# Cent AI serves its OpenAI-compatible API under /v1, so the
# base is just the host; the relay appends the /v1/* path as-is.
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
