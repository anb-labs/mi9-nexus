"""HTTP tool server for the Mi9-Nexus webapp.

Exposes the agentic tools (run_python, retrieve, web_search, web_fetch) as a tiny
localhost JSON API so the zero-dependency browser UI can run a real tool loop
without talking to llama.cpp directly or re-implementing the sandbox in Node.

Run:  .venv/bin/python -m nexus.toolserver   (listens on 127.0.0.1:8090)
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import memory, office, sandbox, web

PORT = 8090


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
                chat_id = str(body.get("chat_id", "default"))[:64].replace("/", "_")
                workdir = f"/tmp/mi9-sandbox/{chat_id}"
                r = sandbox.run_script_dir(body.get("code", ""), workdir)
                return self._send({"stdout": r.get("stdout", ""),
                                   "error": r.get("error", "")})
            if path == "/retrieve":
                hits = memory.query(body.get("query", ""), k=5)
                return self._send({"hits": [{"path": h["path"], "text": h["text"][:800]}
                                            for h in hits]})
            if path == "/web_search":
                return self._send({"hits": web.search(body.get("query", ""), limit=5)})
            if path == "/web_fetch":
                return self._send({"text": web.fetch(body.get("url", ""), max_chars=3000)})
            if path == "/office_read":
                return self._send({"text": office.extract(body.get("path", ""), max_chars=8000)})
            self._send({"error": f"unknown tool {path}"}, 404)
        except Exception as e:
            self._send({"error": f"{type(e).__name__}: {e}"}, 500)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print(f"Mi9-Nexus tool server on http://127.0.0.1:{PORT}")
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()