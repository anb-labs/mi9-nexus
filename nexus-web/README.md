# Mi9-Nexus Web UI

A local, agentic chat interface for the **Mi9-Nexus** model (llama.cpp server).
Zero-dependency Node server + single-page app.

## Run

```sh
# 1. model server (llama.cpp) on :8080
cd ~/Mi9/mi9-ai-model && nexus/serve &

# 2. tool server (sandboxed python / retrieval / web) on :8090
cd ~/Mi9/mi9-ai-model && .venv/bin/python -m nexus.toolserver &

# 3. web UI on :3000
cd ~/Mi9/nexus-web && node server.js
# open http://localhost:3000
```

## Architecture

- `server.js` — zero-dependency Node server: serves the static UI and proxies
  `/v1/*` → llama.cpp (`:8080`) and `/tools/*` → the tool server (`:8090`).
- `nexus/toolserver.py` (in mi9-ai-model) — exposes the agentic tools as a tiny
  localhost JSON API: `run_python`, `retrieve`, `web_search`, `web_fetch`.
- `index.html` — the single-page app with a **client-side agent loop**: the model
  emits `<tool>{...}</tool>` calls, the UI executes them via `/tools/*`, shows
  each call + result as a tool card, feeds the result back, and repeats until the
  model gives a final answer.

## Features

- **Agentic tool loop** — the model can run Python, search the local corpus, and
  search/fetch the web, with every tool call and result shown inline.
- Streaming responses (SSE), markdown + code highlighting.
- **think** toggle — deep mode (`enable_thinking: true`) vs. fast mode.
- Temperature slider, max-tokens selector.
- Token count, response time, tok/s per message.
- Chat history kept in the page (clear / export as JSON).
- Health indicator (pings `/v1/health`).

## Notes

- zero dependencies (Node >= 18); no build step.
- marked + highlight.js + Inter font load from CDN (internet on first load).
- the model is a 1.7B local model — a specialist (code, tool-use,
  executor-verified tasks), not a general chatbot.
- override upstreams with `NEXUS_UPSTREAM` / `NEXUS_TOOLS`.