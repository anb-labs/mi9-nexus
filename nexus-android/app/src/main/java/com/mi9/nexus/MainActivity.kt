package com.mi9.nexus

import android.annotation.SuppressLint
import android.app.Activity
import android.graphics.Color
import android.graphics.Typeface
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.webkit.ConsoleMessage
import android.webkit.WebChromeClient
import android.webkit.WebResourceError
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.TextView
import java.io.File

/**
 * Mi9-Nexus Android shell.
 *
 * First run shows a setup screen that downloads the model (~1.8 GB, from HuggingFace)
 * and prepares the PRoot + Alpine sandbox. Once both are ready it starts the local
 * server (llama.cpp + tools) and loads the webapp in a WebView.
 */
class MainActivity : Activity() {

    private var webView: WebView? = null
    private var server: LocalServer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null && needsSetup()) showFirstRun() else startApp()
    }

    private fun needsSetup(): Boolean =
        !ModelDownloader.isComplete(this) || !AlpineSetup.isReady(this) ||
            !AlpineSetup.toolchainReady(this)

    // ---- first-run setup screen ------------------------------------------

    private fun showFirstRun() {
        val bg = Color.parseColor("#0B0B0D")
        val accent = Color.parseColor("#E10600")
        val fg = Color.parseColor("#F2F2F5")
        val muted = Color.parseColor("#8A8A99")

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(64, 80, 64, 80)
            setBackgroundColor(bg)
            keepScreenOn = true
        }

        val title = TextView(this).apply {
            text = "Mi9·Nexus"; setTextColor(accent); textSize = 34f
            typeface = Typeface.DEFAULT_BOLD; gravity = Gravity.CENTER
        }
        val subtitle = TextView(this).apply {
            text = "Runs the model locally on your device.\nThe first setup downloads ~1.8 GB (model) and a Linux sandbox."
            setTextColor(muted); gravity = Gravity.CENTER; textSize = 14f
        }

        val modelLabel = TextView(this).apply { textSize = 15f; setTextColor(fg) }
        val modelBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 1000 }
        val sandboxLabel = TextView(this).apply { textSize = 15f; setTextColor(fg) }
        val sandboxBar = ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal).apply { max = 1000 }
        val button = Button(this).apply { text = "Download & set up" }

        modelLabel.text = if (ModelDownloader.isComplete(this)) "Model: ready" else "Model: not downloaded (~1.8 GB)"
        sandboxLabel.text = if (AlpineSetup.isReady(this)) "Linux sandbox: ready" else "Linux sandbox: not set up"
        modelBar.progress = if (ModelDownloader.isComplete(this)) 1000 else 0
        sandboxBar.progress = if (AlpineSetup.isReady(this)) 1000 else 0

        root.addView(title)
        root.addView(subtitle)
        root.addView(spacer(24))
        root.addView(modelLabel)
        root.addView(modelBar)
        root.addView(spacer(16))
        root.addView(sandboxLabel)
        root.addView(sandboxBar)
        root.addView(spacer(32))
        root.addView(button)
        setContentView(root)

        button.setOnClickListener {
            button.isEnabled = false
            button.text = "Setting up…"
            Thread {
                val ok = doSetup { ml, mf, sl, sf ->
                    runOnUiThread {
                        modelLabel.text = ml; modelBar.progress = (mf * 1000).toInt()
                        sandboxLabel.text = sl; sandboxBar.progress = (sf * 1000).toInt()
                    }
                }
                runOnUiThread {
                    if (ok) startApp() else { button.isEnabled = true; button.text = "Retry" }
                }
            }.apply { isDaemon = true }.start()
        }
    }

    /** Download model + set up Alpine. Calls [update] on progress. Returns true on success. */
    private fun doSetup(
        update: (modelLabel: String, modelFrac: Float, sandboxLabel: String, sandboxFrac: Float) -> Unit,
    ): Boolean {
        android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND)

        var modelLabel = if (ModelDownloader.isComplete(this)) "Model: ready" else "Model: downloading… 0%"
        var modelFrac = if (ModelDownloader.isComplete(this)) 1f else 0f
        var sandboxLabel = if (AlpineSetup.isReady(this)) "Linux sandbox: ready" else "Linux sandbox: preparing…"
        var sandboxFrac = if (AlpineSetup.isReady(this)) 1f else 0f
        update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)

        if (!ModelDownloader.isComplete(this)) {
            val r = ModelDownloader.download(this) { p ->
                modelFrac = p.fraction
                modelLabel = if (p.total > 0)
                    "Model: ${"%.0f".format(p.downloaded / 1e6)} / ${"%.0f".format(p.total / 1e6)} MB (${(p.fraction * 100).toInt()}%)"
                else "Model: downloading… ${(p.fraction * 100).toInt()}%"
                update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
            }
            if (r.isFailure) {
                val m = r.exceptionOrNull()?.message ?: "error"
                modelLabel = "Model: failed ($m)"
                update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
                return false
            }
            modelLabel = "Model: ready"; modelFrac = 1f
        }
        update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)

        if (!AlpineSetup.isReady(this)) {
            val r = AlpineSetup.ensureReady(this) { p ->
                sandboxFrac = p.fraction
                sandboxLabel = "Linux sandbox: ${p.stage} (${(p.fraction * 100).toInt()}%)"
                update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
            }
            if (r.isFailure) {
                sandboxLabel = "Linux sandbox: failed (${r.exceptionOrNull()?.message})"
                update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
                return false
            }
            sandboxLabel = "Linux sandbox: ready"; sandboxFrac = 1f
        }
        update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)

        if (!AlpineSetup.toolchainReady(this)) {
            sandboxLabel = "Linux sandbox: installing Python…"; sandboxFrac = 0.5f
            update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
            val r = AlpineSetup.setupToolchain(this) { stage ->
                sandboxLabel = "Linux sandbox: $stage"
                update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
            }
            if (r.isFailure) {
                sandboxLabel = "Linux sandbox: toolchain failed (${r.exceptionOrNull()?.message})"
                update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
                return false
            }
            sandboxLabel = "Linux sandbox: ready"; sandboxFrac = 1f
        }
        update(modelLabel, modelFrac, sandboxLabel, sandboxFrac)
        return true
    }

    private fun spacer(h: Int): View = View(this).apply { layoutParams = LinearLayout.LayoutParams(1, h) }

    // ---- main app --------------------------------------------------------

    @SuppressLint("SetJavaScriptEnabled")
    private fun startApp() {
        val wv = WebView(this)
        webView = wv
        setContentView(wv)

        wv.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            javaScriptCanOpenWindowsAutomatically = true
            allowFileAccess = false
            allowContentAccess = false
            cacheMode = WebSettings.LOAD_DEFAULT
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            mediaPlaybackRequiresUserGesture = false
        }

        wv.webViewClient = object : WebViewClient() {
            override fun onPageFinished(view: WebView, url: String) {
                Log.i(TAG, "pageFinished $url")
            }
            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                Log.e(TAG, "recvError ${error.errorCode} ${error.description} ${request.url}")
            }
        }
        wv.webChromeClient = object : WebChromeClient() {
            override fun onConsoleMessage(cm: ConsoleMessage): Boolean {
                Log.i(TAG, "console[${cm.messageLevel()}] ${cm.message()} @${cm.sourceId()}:${cm.lineNumber()}")
                return true
            }
        }

        val local = LocalServer(
            assets = assets,
            backendHost = BuildConfig.BACKEND_HOST,
            backendPort = BuildConfig.BACKEND_PORT,
            toolsHost = BuildConfig.TOOLS_HOST,
            toolsPort = BuildConfig.TOOLS_PORT,
        )
        server = local
        // The in-Alpine tool server doesn't survive app restarts; relaunch it.
        if (AlpineSetup.toolchainReady(this) && !AlpineSetup.toolServerUp) {
            Thread { AlpineSetup.startToolServer(this) }.apply { isDaemon = true }.start()
        }
        local.start { port ->
            runOnUiThread {
                if (!isFinishing) {
                    wv.loadUrl("http://127.0.0.1:$port/webapp/index.html")
                    loadModelAsync()
                }
            }
        }
    }

    /** Load the downloaded GGUF into llama.cpp off the UI thread. */
    private fun loadModelAsync() {
        val model = File(filesDir, "model.gguf")
        if (!model.exists()) return
        Thread {
            android.os.Process.setThreadPriority(android.os.Process.THREAD_PRIORITY_BACKGROUND)
            Log.i(TAG, "loading native model (${model.length()} bytes)")
            val ok = NativeLlama.bootstrap(applicationInfo.nativeLibraryDir, model.absolutePath)
            Log.i(TAG, "native model ready=$ok")
        }.apply { isDaemon = true }.start()
    }

    @Suppress("DEPRECATION")
    override fun onBackPressed() {
        val wv = webView
        if (wv != null && wv.canGoBack()) wv.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        server?.stop()
        AlpineSetup.stopToolServer()
        webView?.destroy()
        super.onDestroy()
    }

    private companion object {
        const val TAG = "Mi9Web"
    }
}