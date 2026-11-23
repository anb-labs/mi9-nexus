#!/usr/bin/env node
/**
 * Mi9-Nexus web UI server.
 *
 * Zero dependencies: serves the static UI and proxies /v1/* to the local
 * llama.cpp server (default http://127.0.0.1:8080), so the browser never
 * talks to llama.cpp directly (no CORS issues, no API key in the page).
 *
 * Run:  node server.js [port]   (default 3000)
 * Then: open http://localhost:3000
 */
const http = require("http");
const fs = require("fs");
const path = require("path");

const PORT = parseInt(process.argv[2] || process.env.PORT || "3000", 10);
const UPSTREAM = process.env.NEXUS_UPSTREAM || "http://127.0.0.1:8080";
const TOOL_UPSTREAM = process.env.NEXUS_TOOLS || "http://127.0.0.1:8090";
const ROOT = __dirname;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
};

function proxy(req, res, base, stripPrefix) {
  let path = req.url;
  if (stripPrefix && path.startsWith(stripPrefix)) path = path.slice(stripPrefix.length) || "/";
  const url = new URL(path, base);
  const mod = url.protocol === "https:" ? require("https") : require("http");
  const upstream = mod.request(
    {
      hostname: url.hostname,
      port: url.port || (url.protocol === "https:" ? 443 : 80),
      path: url.pathname + url.search,
      method: req.method,
      headers: { ...req.headers, host: url.host },
    },
    (up) => {
      res.writeHead(up.statusCode || 502, up.headers);
      up.pipe(res);
    }
  );
  upstream.on("error", (e) => {
    res.writeHead(502, { "content-type": "application/json" });
    res.end(JSON.stringify({ error: `upstream unreachable: ${e.message}` }));
  });
  req.pipe(upstream);
}

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (url.pathname.startsWith("/v1/")) return proxy(req, res, UPSTREAM, null);
  if (url.pathname.startsWith("/tools/")) return proxy(req, res, TOOL_UPSTREAM, "/tools");

  let fp = path.join(ROOT, url.pathname === "/" ? "index.html" : url.pathname);
  if (!fp.startsWith(ROOT)) {
    res.writeHead(403);
    return res.end("forbidden");
  }
  fs.readFile(fp, (err, data) => {
    if (err) {
      res.writeHead(404, { "content-type": "text/plain" });
      return res.end("not found");
    }
    res.writeHead(200, {
      "content-type": MIME[path.extname(fp)] || "application/octet-stream",
    });
    res.end(data);
  });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`Mi9-Nexus web UI: http://localhost:${PORT}`);
  console.log(`  proxying /v1/* -> ${UPSTREAM}`);
  console.log(`  proxying /tools/* -> ${TOOL_UPSTREAM}`);
});