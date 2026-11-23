# Mi9-Nexus — Desktop (Tauri 2.0)

A Tauri 2.0 desktop app for Linux/macOS/Windows that bundles the Mi9-Nexus webapp
and a native llama.cpp server. It's self-contained: no host llama.cpp required.

## Architecture

```
WebView  ->  http://127.0.0.1:<port>/        (tiny_http server in Rust)
                 |  serves the embedded webapp (include_dir! -> frontend/)
                 |  /v1/*   -> reverse-proxy -> llama-server sidecar (127.0.0.1:18080)
                 |  /tools/* -> reverse-proxy -> tool server (127.0.0.1:8090)
llama-server (bundled sidecar, libllama statically linked) loads the GGUF
model from dirs::data_local_dir()/mi9-nexus/model.gguf (downloaded from R2 on first run)
```

## Prerequisites (Arch)

```bash
sudo pacman -S rust            # rustc + cargo
# webkit2gtk-4.1, libsoup3, rsvg2 (already present on this machine)
npm i -g @tauri-apps/cli@2     # tauri CLI
```

## Build & run

```bash
cd src-tauri
cargo build                    # dev binary -> target/debug/app
./target/debug/app             # run (opens the window)
# or:  tauri dev               # (from ~/Mi9/nexus-desktop)
```

## The llama.cpp sidecar

`binaries/llama-server-x86_64-unknown-linux-gnu` is a **static** llama.cpp server
(only system libs). To rebuild it:

```bash
cd third_party/llama.cpp
cmake -B build-linux -S . -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release -DGGML_NATIVE=ON -DBUILD_SHARED_LIBS=OFF \
  -DLLAMA_BUILD_TOOLS=ON -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_EXAMPLES=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_CURL=OFF -DGGML_OPENMP=OFF
cmake --build build-linux --target llama-server -j"$(nproc)"
cp build-linux/bin/llama-server \
   <repo>/src-tauri/binaries/llama-server-<target-triple>
```

## Model

Bundled/downloaded from Cloudflare R2:
`https://pub-d33de59ed2ce4360adf02fc3e0cd87d6.r2.dev/mi9-nexus-v3-Q8_0.gguf`
(1.8 GB Q8_0). Downloaded once into `~/.local/share/mi9-nexus/model.gguf`.

## Not yet done

- Async first-run download (currently blocks setup while downloading).
- `tauri build` -> `.deb` / `.AppImage` (Linux), `.dmg` (macOS), `.msi`/`.exe` (Windows).
- arm64 sidecar build (Apple Silicon / Linux ARM).