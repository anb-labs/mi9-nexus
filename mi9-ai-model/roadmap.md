# Mi9-Nexus Roadmap

> Last updated 2026-11-16. Goal: ship Mi9-Nexus as a cross-platform app (desktop + Android,
> **no iOS for now**). The model is done; the work is the app + agent harness.

## Vision

**Mi9-Nexus** — a cross-platform app that ships with the Mi9-Nexus model (Qwen3-1.7B + LoRA,
Q8_0) and does agentic tasks: **Linux, macOS, Windows, Android.** No iOS (at least not yet).

- **Model:** `mi9-nexus-v3-Q8_0.gguf` (1.83 GB), Q8_0 — keep full power on Android too
  (modern phones have >4 GB RAM; local-AI users have more).
- **Agentic:** the model is a controller — it calls tools (run_python sandbox, retrieval,
  web search/fetch) and verifies results.
- **Sandbox on Android:** PRoot + Alpine Linux (the Horus / Kai approach) — a real Linux
  userland for `run_python`/shell, no root, no host access.

## Current state (verified)

- **Model:** Mi9-Nexus v3, Q8_0 — 86.0% regression (math 67.9, code 100.0, logic 58.3%).
- **Webapp prototype** (`~/Mi9/nexus-web`): zero-dep Node + Python tool server; chats (model-named),
  per-chat sandbox, test-time compute (`--best-of`), modern red/dark UI.
- **Tools:** run_python (sandbox), retrieve (BM25), web_search/web_fetch (obscura), office_read.
- **Test-time compute:** best-of-N + verification (+25 code/text, +11 tool; math_exec 50→75% at k=10).

## Architecture

```
Frontend:  index.html (the webapp) — reused as-is inside a WebView
Backend:   Rust (Tauri 2.0) OR Kotlin (WebView) — runs llama.cpp + tools
Model:     mi9-nexus-v3-Q8_0.gguf — bundled or downloaded on first run
Sandbox:   PRoot + Alpine (Android) / subprocess+rlimits (desktop)
```

**Android sandbox (Horus/Kai pattern):** PRoot + Alpine (~3 MB) gives a real Linux userland.
`run_python` executes inside it. No root, no host access. llama.cpp runs natively (Android JNI)
for speed; the tool server + webapp can run in the Alpine or natively.

## Goals (one at a time)

1. **Android app scaffold** — Kotlin WebView app + PRoot Alpine setup (download → verify → extract)
  + the webapp in a WebView. [Horus/Kai pattern]
2. **llama.cpp on Android** — native JNI (examples/llama.android), load the Q8_0 model.
3. **Tool server on Android** — run_python inside the PRoot Alpine; retrieve/web tools.
4. **Desktop (Tauri 2.0)** — Linux/macOS/Windows; reuse the webapp; bundle llama.cpp.
5. **Model distribution** — download on first run (GitHub/HF), checksum verify.
6. **Packaging** — APK (direct), .deb/.AppImage, .dmg, .msi.

## Key constraints

- **No iOS** (App Store $99/yr; revisit later).
- **Android full power** — Q8_0, no quant reduction.
- **Sandbox = PRoot + Alpine** (Horus/Kai), not a toy interpreter.
- **Model download** (1.83 GB) on first run — the main UX hurdle.

## Key insight

The weights are done (86% at Q8_0). The leverage is the harness (tools + test-time compute +
sandbox + memory). Ship the harness, not more LoRA.