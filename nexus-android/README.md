# Mi9-Nexus — Android app (Goal 1 scaffold)

Kotlin WebView shell that bundles the Mi9-Nexus webapp and runs the PRoot + Alpine
sandbox (the Horus / Kai pattern). This is Goal 1 of the roadmap: the Android scaffold.

## What's here

- `MainActivity` — WebView that loads `assets/webapp/index.html` and:
  - serves bundled assets under `https://appassets.androidplatform.net/webapp/*`
  - reverse-proxies `/v1/*` → llama.cpp and `/tools/*` → the tool server
    (hosts/ports come from `BuildConfig`, default `10.0.2.2` = host loopback on the
    Android emulator).
- `AlpineSetup` — downloads + SHA-256-verifies + extracts an Alpine minirootfs into
  app-private storage, and locates the bundled `proot` (`jniLibs/<abi>/libproot.so`).
  It does **not** run automatically — call `AlpineSetup.ensureReady(context) { ... }`
  when the user agrees to spend the download.

## Build

```bash
export ANDROID_HOME=$HOME/Android/Sdk
./gradlew assembleDebug          # -> app/build/outputs/apk/debug/app-debug.apk
./gradlew installDebug           # install on a connected device/emulator
```

Requires: JDK 17+ (built with 21), Android SDK platform 35 + build-tools 35.0.0,
Gradle 8.9 (via the wrapper).

## Model hosting (Cloudflare R2)

The GGUF is hosted on a public Cloudflare R2 bucket:
`https://pub-d33de59ed2ce4360adf02fc3e0cd87d6.r2.dev/mi9-nexus-v3-Q8_0.gguf`

`ModelDownloader.MODEL_URL` points at it; the first-run screen downloads it (resumable)
into `filesDir/model.gguf`.

To re-upload (rclone):

```bash
export RCLONE=$HOME/.local/bin/rclone
# one-time: rclone config create r2 s3 provider=Cloudflare \
#   access_key_id=... secret_access_key=... endpoint=https://<account>.r2.cloudflarestorage.com
$RCLONE config update r2 region=auto
$RCLONE copy models/mi9-nexus-v3-Q8_0.gguf r2:mi9-nexus \
  --s3-no-check-bucket --s3-chunk-size=16M --transfers 4
```

## Not yet done (later goals)

- **Goal 2:** native llama.cpp (JNI) so `/v1/*` is served on-device (no LAN host).
- **Goal 3:** run tools (`run_python` etc.) inside the PRoot Alpine.
- Vendor marked / highlight.js / fonts for offline use.
- Bundle an Android `proot` binary as `jniLibs/<abi>/libproot.so`.