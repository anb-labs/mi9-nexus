# Mi9-Nexus

A small, local AI that runs on ordinary hardware — a 1.7B model plus an agent
harness that lets it run code, search the web, and read documents, fully offline.

- **Model:** `mi9-nexus-v3-Q8_0.gguf` (Qwen3-1.7B + LoRA), Q8_0, ~1.83 GB.
  Distributed separately (see below) — not stored in this repo.
- **Harness:** tools (`run_python` sandbox, retrieval, web search/fetch, office-doc
  reading), test-time compute (sample + verify), and a regression gate.
- **Platforms:** Linux desktop (Tauri 2.0) and Android (Kotlin WebView + native
  llama.cpp + PRoot/Alpine sandbox).

Measured on a CPU-only laptop: 86.0% on the regression suite (code 100%, math 67.9%,
logic 58.3%); ~16.5 tok/s decode.

## Layout

| Path | What it is |
|------|------------|
| `mi9-ai-model/` | The model program: training/growth loop, agent loop, tool server, eval suites, corpus, reports. |
| `nexus-web/` | The web UI (zero-dependency Node server + single-page app). |
| `nexus-desktop/` | Desktop app (Tauri 2.0 / Rust) that bundles llama.cpp + the webapp. |
| `nexus-android/` | Android app (Kotlin) — native llama.cpp + PRoot/Alpine tool sandbox. |
| `demo-video/` | The demo-video script / screenplay. |

## Quick start (web UI, from source)

```sh
# 1. model server (llama.cpp) on :8080
cd mi9-ai-model && nexus/serve

# 2. tool server on :8090
cd mi9-ai-model && .venv/bin/python -m nexus.toolserver

# 3. web UI on :3000 -> open http://localhost:3000
cd nexus-web && node server.js
```

The model weights are downloaded on first run by the desktop/Android apps, and can
also be fetched directly from the project's public mirror
(`https://pub-d33de59ed2ce4360adf02fc3e0cd87d6.r2.dev/mi9-nexus-v3-Q8_0.gguf`).

See each subproject's own `README.md` for build/run details.

## License — source-available, non-commercial

This project is licensed under the **PolyForm Noncommercial License 1.0.0** (see
[`LICENSE`](LICENSE)). In plain terms:

- You may **read, use, modify, and share** the code for **non-commercial** purposes
  (research, personal study, education, hobby projects, etc.).
- **Commercial use is not permitted** without a separate license from the copyright
  holder. If you want to build a business or product on this, contact
  `angshu.roy.1910@gmail.com` to discuss a license.

> Required Notice: Copyright 2026 anb-labs (https://github.com/anb-labs).

## A note on forks

This repository is published for reading and non-commercial experimentation.
**Forks are not officially recognized or endorsed by anb-labs.** Nothing in the
license prevents you from exercising the rights it grants for non-commercial use,
but anb-labs does not review, support, or claim any fork.

## What is *not* in this repo

To keep it source-only, the following are intentionally excluded and must be
generated or fetched to build/run:

- **Model weights** (`mi9-ai-model/models/` — 1.8 GB; fetch from the R2 mirror).
- **LoRA adapters** (`mi9-ai-model/adapters/` — training outputs).
- **Android `third_party/llama.cpp`** (clone llama.cpp there; it is a build dependency).
- **The desktop llama-server sidecar** (`src-tauri/binaries/`) and Rust `target/`.
- **All signing keys and secrets** (`credentials/`, `*.keystore`, `keystore.properties`).
  These are private and are never included.