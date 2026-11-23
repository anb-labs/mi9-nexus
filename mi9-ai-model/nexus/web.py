"""Web research via the obscura headless browser — no API keys, no extra installs.

Provides `search` (DuckDuckGo HTML) and `fetch` (URL -> text) for the agent's
web tool. Runs on the host network (outside the sandbox, like `retrieve`).
"""
import html
import re
import shutil
import subprocess
import urllib.parse

OBSCURA = shutil.which("obscura") or "/home/santosh/.local/bin/obscura"


def _run(args, timeout=60):
    try:
        p = subprocess.run([OBSCURA] + args, capture_output=True, text=True,
                           timeout=timeout)
        return p.stdout or ""
    except Exception as e:
        return f"[web error: {type(e).__name__}: {e}]"


def search(query, limit=5):
    """Return [{title, url, snippet}] for a web query (DuckDuckGo HTML)."""
    q = urllib.parse.quote(query)
    raw = _run(["fetch", f"https://html.duckduckgo.com/html/?q={q}",
                "--dump", "original"])
    if raw.startswith("[web error"):
        return [{"title": "search failed", "url": "", "snippet": raw}]
    items = re.findall(r'result__a"\s+href="([^"]+)"[^>]*>(.*?)</a>', raw, re.S)
    snippets = re.findall(r'result__snippet"[^>]*>(.*?)</a>', raw, re.S)
    out = []
    for i, (href, title) in enumerate(items[:limit]):
        m = re.search(r'uddg=([^&]+)', href)
        url = urllib.parse.unquote(m.group(1)) if m else href
        title = re.sub(r'<[^>]+>', '', html.unescape(title)).strip()
        snip = ""
        if i < len(snippets):
            snip = re.sub(r'<[^>]+>', '', html.unescape(snippets[i])).strip()
        out.append({"title": title, "url": url, "snippet": snip[:300]})
    return out


def fetch(url, max_chars=4000):
    """Fetch a URL and return its visible text (truncated)."""
    raw = _run(["fetch", url, "--dump", "text"])
    if raw.startswith("[web error"):
        return raw
    return raw[:max_chars]