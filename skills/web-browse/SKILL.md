# Web Browse

Use this skill when the user asks Hermes to open, read, check, or summarise
a website or a page URL.

Hermes has NO real browser (no Chromium, no clicks, no logins) in this
container. "Opening" a website means: fetch the page over HTTP and read
its text. That covers articles, docs, homepages, price pages, and most
public pages. It does NOT cover: logging in to an account, clicking
buttons/forms, checkouts, or pages that only render after logging in.

## How to open a page

Run the helper (stdlib-only Python, no extra install):

```
python3 skills/web-browse/scripts/fetch.py <URL>
```

It prints the page title + readable text (HTML tags, scripts, styles and
navigation stripped), truncated to about 8,000 characters. Read that
output and answer the user from it. Never paste raw HTML back to the user.

Rules:
- Always use the helper. Do not guess a page's content from the URL or
  from memory — fetch it first.
- If the helper reports an error (404, timeout, blocked), say so plainly
  and do not invent the content.
- If the page looks empty or says JavaScript is required, retry once with
  the reader fallback (renders JS server-side, free):
  ```
  python3 skills/web-browse/scripts/fetch.py --reader <URL>
  ```
  If the reader also fails (it is blocked in some regions), say so and stop.
- One fetch per page. Do not hammer a site: if a second fetch fails too,
  stop and report it.
- Never submit forms, never enter credentials, never use this to log in
  anywhere. Reading only.
- Keep the user's question in mind: fetch the page, then answer what they
  actually asked (summary, a specific fact, whether something is listed,
  ...), don't just dump the whole text.
