// Mi9-Nexus desktop backend.
//
// - Serves the bundled webapp over a loopback HTTP server (embedded via include_dir!).
// - Reverse-proxies /v1/* -> the on-device llama-server sidecar (127.0.0.1:18080)
//   and /tools/* -> the tool server (127.0.0.1:8090).
// - On first run, downloads the GGUF from Cloudflare R2 into the app data dir, then
//   spawns llama-server as a bundled sidecar. While it's downloading/loading, /v1/health
//   reports "loading" so the webapp shows a progress state instead of "server down".
// - The Tauri window loads http://127.0.0.1:<port>/ so the webapp's fetches are
//   same-origin.

use include_dir::{include_dir, Dir};
use std::io::Read;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Mutex;
use tauri::{RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;
use tiny_http::{Header, Response, Server};

static FRONTEND: Dir<'_> = include_dir!("$CARGO_MANIFEST_DIR/../frontend");
static LLAMA_CHILD: Mutex<Option<CommandChild>> = Mutex::new(None);
static LLAMA_READY: AtomicBool = AtomicBool::new(false);
static DOWNLOAD_DONE: AtomicU64 = AtomicU64::new(0);
static DOWNLOAD_TOTAL: AtomicU64 = AtomicU64::new(0);

const BACKEND_HOST: &str = "127.0.0.1";
const BACKEND_PORT: u16 = 18080; // desktop llama-server sidecar
const TOOLS_PORT: u16 = 8090; // tool server
const MODEL_URL: &str =
    "https://pub-d33de59ed2ce4360adf02fc3e0cd87d6.r2.dev/mi9-nexus-v3-Q8_0.gguf";
const MODEL_FILE: &str = "mi9-nexus-v3-Q8_0.gguf";
const EXPECTED_SIZE: u64 = 1_834_426_304;

const DOWNLOADING_HTML: &str = r#"<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mi9-Nexus</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin:0; height:100vh; display:flex; align-items:center; justify-content:center;
    background:#08080b; color:#f2f2f5; font-family: Inter, system-ui, sans-serif; }
  .wrap { width:min(520px, 86vw); text-align:center; }
  h1 { font-size:34px; margin:0 0 6px; letter-spacing:-0.5px; }
  .brand { color:#ff2d55; }
  p { color:#8a8a99; margin:8px 0; font-size:15px; }
  .bar { height:10px; border-radius:6px; background:#1a1a22; overflow:hidden; margin:18px 0 10px; }
  #fill { height:100%; width:0%; background:linear-gradient(90deg,#ff2d55,#ff5e62); transition:width .3s; }
  #pct { font-size:13px; color:#8a8a99; font-variant-numeric:tabular-nums; }
</style></head>
<body>
<div class="wrap">
  <h1><span class="brand">Mi9</span>·Nexus</h1>
  <p id="msg">Preparing your model…</p>
  <div class="bar"><div id="fill"></div></div>
  <p id="pct">0%</p>
</div>
<script>
async function tick() {
  try {
    const r = await fetch("/v1/health");
    const j = await r.json();
    if (j.status === "ok") { location.reload(); return; }
    if (j.total > 0) {
      const pct = Math.min(100, Math.round(100 * j.downloaded / j.total));
      document.getElementById("fill").style.width = pct + "%";
      document.getElementById("pct").textContent = pct + "%";
      const mb = (j.downloaded/1e6).toFixed(0), tot = (j.total/1e6).toFixed(0);
      document.getElementById("msg").textContent = "Downloading the model… " + mb + " / " + tot + " MB";
    }
  } catch (e) {}
  setTimeout(tick, 1000);
}
tick();
</script>
</body></html>"#;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let port = start_server();
            spawn_llama_async(app.handle().clone());
            let url = format!("http://127.0.0.1:{}/", port);
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url.parse().unwrap()))
                .title("Mi9-Nexus")
                .inner_size(1200.0, 820.0)
                .min_inner_size(900.0, 600.0)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|_app_handle, event| {
        if let RunEvent::Exit = event {
            if let Some(child) = LLAMA_CHILD.lock().unwrap().take() {
                let _ = child.kill();
            }
        }
    });
}

fn start_server() -> u16 {
    let server = std::sync::Arc::new(Server::http(("127.0.0.1", 0)).expect("bind loopback"));
    let port = server.server_addr().to_ip().unwrap().port();
    let s = server.clone();
    std::thread::spawn(move || {
        for req in s.incoming_requests() {
            handle(req);
        }
    });
    println!("Mi9-Nexus serving on http://127.0.0.1:{}", port);
    port
}

fn handle(mut req: tiny_http::Request) {
    let method = req.method().to_string();
    let url = req.url().to_string();
    let mut body = Vec::new();
    let _ = req.as_reader().read_to_end(&mut body);

    // While the model is downloading/loading, report a friendly "loading" state with progress.
    if url.starts_with("/v1/health") && !LLAMA_READY.load(Ordering::SeqCst) {
        let done = DOWNLOAD_DONE.load(Ordering::SeqCst);
        let total = DOWNLOAD_TOTAL.load(Ordering::SeqCst);
        let body = format!(
            "{{\"status\":\"loading\",\"downloaded\":{},\"total\":{}}}",
            done, total
        );
        let resp = Response::from_string(body)
            .with_status_code(200)
            .with_header(Header::from_bytes("Content-Type", "application/json").unwrap());
        let _ = req.respond(resp);
        return;
    }

    if url.starts_with("/v1/") || url.starts_with("/tools/") {
        proxy(req, &method, &url, body);
    } else {
        serve_asset(req, &url);
    }
}

fn serve_asset(req: tiny_http::Request, url: &str) {
    let name = url.split('?').next().unwrap_or(url);
    let mut path = name.trim_start_matches('/');
    if path.is_empty() {
        path = "index.html";
    }
    // While the model is downloading/loading, serve a progress page instead of the app.
    if !LLAMA_READY.load(Ordering::SeqCst) && (path == "index.html" || path == "webapp/index.html")
    {
        let resp = Response::from_data(DOWNLOADING_HTML.as_bytes())
            .with_status_code(200)
            .with_header(Header::from_bytes("Content-Type", "text/html; charset=utf-8").unwrap());
        let _ = req.respond(resp);
        return;
    }
    match FRONTEND.get_file(path) {
        Some(f) => {
            let ct = Header::from_bytes("Content-Type", mime_for(path)).unwrap();
            let resp = Response::from_data(f.contents())
                .with_status_code(200)
                .with_header(ct);
            let _ = req.respond(resp);
        }
        None => {
            let _ = req.respond(Response::from_string("not found").with_status_code(404));
        }
    }
}

fn proxy(req: tiny_http::Request, method: &str, url: &str, body: Vec<u8>) {
    let port = if url.starts_with("/tools/") {
        TOOLS_PORT
    } else {
        BACKEND_PORT
    };
    let target = format!("http://{}:{}{}", BACKEND_HOST, port, url);
    let r = ureq::request(method, &target);
    let result = if body.is_empty() {
        r.call()
    } else {
        r.send_bytes(&body)
    };
    match result {
        Ok(resp) => {
            let status = resp.status();
            let ct = resp.content_type().to_string();
            let reader = resp.into_reader();
            let hdr = Header::from_bytes("Content-Type", ct).unwrap();
            let out = Response::new(tiny_http::StatusCode(status), vec![hdr], reader, None, None);
            let _ = req.respond(out);
        }
        Err(e) => {
            let msg = format!("{{\"error\":\"backend unreachable: {}\"}}", e);
            let _ = req.respond(Response::from_string(msg).with_status_code(503));
        }
    }
}

// ---- llama-server sidecar -------------------------------------------------

fn spawn_llama_async(app: tauri::AppHandle) {
    std::thread::spawn(move || {
        let model = match find_model() {
            Some(m) => m,
            None => {
                println!("could not obtain the model; /v1 will not be served locally");
                return;
            }
        };
        match app.shell().sidecar("llama-server") {
            Ok(cmd) => {
                let port = BACKEND_PORT.to_string();
                match cmd
                    .args([
                        "-m",
                        model.as_str(),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        port.as_str(),
                        "--ctx-size",
                        "4096",
                        "--jinja",
                    ])
                    .spawn()
                {
                    Ok((_rx, child)) => {
                        *LLAMA_CHILD.lock().unwrap() = Some(child);
                        LLAMA_READY.store(true, Ordering::SeqCst);
                        println!("llama-server ready (model: {})", model);
                    }
                    Err(e) => println!("failed to spawn llama-server: {}", e),
                }
            }
            Err(e) => println!("sidecar 'llama-server' not found: {}", e),
        }
    });
}

fn model_path() -> Option<std::path::PathBuf> {
    let p = dirs::data_local_dir()?.join("mi9-nexus").join(MODEL_FILE);
    match std::fs::metadata(&p) {
        Ok(m) if m.len() == EXPECTED_SIZE => Some(p),
        _ => None,
    }
}

fn find_model() -> Option<String> {
    if let Some(p) = model_path() {
        return Some(p.to_string_lossy().to_string());
    }
    // First run: download from R2 into the app data dir.
    let dir = dirs::data_local_dir()?.join("mi9-nexus");
    std::fs::create_dir_all(&dir).ok()?;
    let dest = dir.join(MODEL_FILE);
    println!("downloading model from {} ...", MODEL_URL);
    match download(MODEL_URL, &dest) {
        Ok(_) => {
            let len = std::fs::metadata(&dest).map(|m| m.len()).unwrap_or(0);
            println!("model downloaded: {} bytes", len);
            Some(dest.to_string_lossy().to_string())
        }
        Err(e) => {
            println!("model download failed: {}", e);
            None
        }
    }
}

fn download(url: &str, dest: &std::path::Path) -> Result<(), Box<dyn std::error::Error>> {
    use std::io::Write;
    let mut last_err = String::from("unknown");
    for attempt in 1..=4 {
        DOWNLOAD_DONE.store(0, Ordering::SeqCst);
        let resp = ureq::get(url).call()?;
        let total = resp
            .header("Content-Length")
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(0);
        DOWNLOAD_TOTAL.store(total, Ordering::SeqCst);
        let mut reader = resp.into_reader();
        let mut file = std::fs::File::create(dest)?;
        let mut buf = [0u8; 1 << 16];
        let mut done = 0u64;
        loop {
            let n = reader.read(&mut buf)?;
            if n == 0 {
                break;
            }
            file.write_all(&buf[..n])?;
            done += n as u64;
            DOWNLOAD_DONE.store(done, Ordering::SeqCst);
        }
        let len = std::fs::metadata(dest).map(|m| m.len()).unwrap_or(0);
        if len == EXPECTED_SIZE || (total > 0 && len == total) {
            return Ok(());
        }
        last_err = format!("incomplete download ({}/{} bytes)", len, EXPECTED_SIZE);
        println!("{}; retry {}/4", last_err, attempt);
    }
    Err(last_err.into())
}

fn mime_for(path: &str) -> &'static str {
    match path.rsplit('.').next().unwrap_or("") {
        "html" | "htm" => "text/html; charset=utf-8",
        "js" | "mjs" => "application/javascript; charset=utf-8",
        "css" => "text/css; charset=utf-8",
        "json" => "application/json",
        "svg" => "image/svg+xml",
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "woff" => "font/woff",
        "woff2" => "font/woff2",
        "ttf" => "font/ttf",
        "ico" => "image/x-icon",
        _ => "application/octet-stream",
    }
}