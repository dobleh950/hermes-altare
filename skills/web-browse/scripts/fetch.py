#!/usr/bin/env python3
"""Fetch a web page and print its readable text (title + body).

Stdlib only — no install needed. Usage:
    python3 fetch.py <URL>
    python3 fetch.py --reader <URL>   # via Jina Reader (renders JS pages)

Prints plain text, truncated to ~8000 chars. Exit 0 on success, 1 on error.
"""
import html
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

MAX_BYTES = 500_000
MAX_CHARS = 8000
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raw = raw[:MAX_BYTES]
    charset = "utf-8"
    m = re.search(r"charset=([\w-]+)", ctype)
    if m:
        charset = m.group(1)
    return raw.decode(charset, errors="replace")


def clean_text(page):
    # Drop scripts, styles, noscript blocks and comments.
    page = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", page)
    page = re.sub(r"(?is)<!--.*?-->", " ", page)
    # Title.
    title = ""
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", page)
    if m:
        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip()
    # Keep some structure: headings and paragraphs become newlines.
    page = re.sub(r"(?is)</(h1|h2|h3|h4|p|li|tr|div|section|article)>", "\n", page)
    page = re.sub(r"(?is)<br\s*/?>", "\n", page)
    # Strip remaining tags, unescape entities, collapse whitespace.
    text = re.sub(r"(?is)<[^>]+>", " ", page)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]
    body = "\n".join(lines)
    if title:
        body = f"Title: {title}\n\n{body}"
    return body[:MAX_CHARS]


def main(argv):
    use_reader = False
    args = [a for a in argv if a != "--reader"]
    if len(args) != len(argv):
        use_reader = True
    if len(args) != 1 or not args[0].startswith(("http://", "https://")):
        print("usage: fetch.py [--reader] <https://URL>", file=sys.stderr)
        return 1
    url = args[0]
    if use_reader:
        url = "https://r.jina.ai/" + url
    try:
        page = fetch(url)
    except urllib.error.HTTPError as e:
        print(f"fetch failed: HTTP {e.code} for {url}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001 - report plainly
        print(f"fetch failed: {e}", file=sys.stderr)
        return 1
    if use_reader:
        # Reader already returns markdown-ish text; just trim it.
        print(page[:MAX_CHARS])
        return 0
    text = clean_text(page)
    if not text.strip():
        print("fetch ok but no readable text found (page may need JavaScript; retry with --reader)", file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
