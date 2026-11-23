#!/usr/bin/env python3
"""Mi9-Nexus tool server for Android (runs inside the PRoot + Alpine sandbox).

Stdlib-only so it runs on a bare Alpine (python3) with no pip installs. Exposes the
agentic tools the webapp calls under /tools/*:
  POST /run_python   {code}                -> {stdout, error}
  POST /web_fetch    {url}                 -> {text}
  POST /web_search   {query}               -> {hits:[{title,url,snippet}]}
  POST /office_read  {path}                -> {text}
  GET  /health                             -> {status:"up"}

Binds 127.0.0.1:8090. The app's LocalServer proxies /tools/* here.
"""
import json
import os
import re
import resource
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote
from urllib.request import Request, urlopen

PORT = 8090


# ---- sandbox ---------------------------------------------------------------

def run_python(code: str, timeout: int = 30) -> dict:
    """Run python code in a subprocess with resource limits. Returns {stdout, error}."""
    try:
        def limits():
            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 2))
            resource.setrlimit(resource.RLIMIT_FSIZE, (5 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            resource.setrlimit(resource.RLIMIT_AS, (1024 * 1024 * 1024,) * 2)

        p = subprocess.run(
            [sys.executable, "-I", "-c", code],
            capture_output=True, text=True, timeout=timeout + 3,
            preexec_fn=limits, cwd="/tmp",
        )
        return {"stdout": (p.stdout or "")[:20000], "error": (p.stderr or "")[:8000]}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "error": f"timeout after {timeout}s"}
    except Exception as e:
        return {"stdout": "", "error": f"{type(e).__name__}: {e}"}


# ---- web (stdlib urllib) ---------------------------------------------------

class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag in ("p", "br", "div", "li", "h1", "h2", "h3", "tr"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self):
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n\n", raw)
        return raw.strip()


def _get(url: str, timeout: int = 20) -> str:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0 (Mi9-Nexus)"})
    with urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def web_fetch(url: str, max_chars: int = 6000) -> str:
    try:
        if not url.startswith("http"):
            url = "https://" + url
        html = _get(url)
        p = _Text()
        p.feed(html)
        return p.text()[:max_chars]
    except Exception as e:
        return f"[web error: {type(e).__name__}: {e}]"


def web_search(query: str, limit: int = 5) -> list:
    try:
        html = _get("https://html.duckduckgo.com/html/?q=" + quote(query))
        items = re.findall(r'result__a"\s+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
        snips = re.findall(r'result__snippet"[^>]*>(.*?)</a>', html, re.S)
        out = []
        for i, (href, title) in enumerate(items[:limit]):
            m = re.search(r"uddg=([^&]+)", href)
            from urllib.parse import unquote
            url = unquote(m.group(1)) if m else href
            title = re.sub(r"<[^>]+>", "", title).strip()
            snip = re.sub(r"<[^>]+>", "", snips[i]).strip() if i < len(snips) else ""
            out.append({"title": title, "url": url, "snippet": snip[:300]})
        return out
    except Exception as e:
        return [{"title": "search failed", "url": "", "snippet": str(e)}]


# ---- office ----------------------------------------------------------------

def office_read(path: str, max_chars: int = 8000) -> str:
    try:
        if path.endswith(".docx"):
            with zipfile.ZipFile(path) as z:
                xml = z.read("word/document.xml").decode("utf-8", "replace")
            text = re.sub(r"<w:p[ >]", "\n<w:p ", xml)
            text = re.sub(r"<[^>]+>", "", text)
            return text[:max_chars]
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(max_chars)
    except Exception as e:
        return f"[office error: {type(e).__name__}: {e}]"


# ---- server ----------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            return self._send({"status": "up"})
        self._send({"error": "not found"}, 404)

    def do_POST(self):
        try:
            n = int(self.headers.get("content-length", 0))
            body = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send({"error": "bad json"}, 400)
        path = self.path.rstrip("/")
        try:
            if path == "/run_python":
                return self._send(run_python(body.get("code", "")))
            if path == "/web_fetch":
                return self._send({"text": web_fetch(body.get("url", ""))})
            if path == "/web_search":
                return self._send({"hits": web_search(body.get("query", ""))})
            if path == "/office_read":
                return self._send({"text": office_read(body.get("path", ""))})
            self._send({"error": f"unknown tool {path}"}, 404)
        except Exception as e:
            self._send({"error": f"{type(e).__name__}: {e}"}, 500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Mi9 tool server on 127.0.0.1:{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()