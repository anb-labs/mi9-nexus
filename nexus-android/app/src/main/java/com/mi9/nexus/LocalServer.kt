package com.mi9.nexus

import android.content.res.AssetManager
import android.util.Log
import org.json.JSONObject
import java.io.BufferedOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.net.URL
import java.util.concurrent.Executors

/**
 * A tiny loopback HTTP server for the Mi9-Nexus WebView shell.
 *
 * Serves the bundled webapp and reverse-proxies /v1 (llama.cpp) and /tools (tool
 * server). When a native model is loaded ([NativeLlama.ready]) /v1 is served locally.
 *
 * It speaks HTTP/1.1 with proper keep-alive (Content-Length) for fixed-size responses
 * and Connection: close for streamed ones (SSE chat, proxy). This matters: Android
 * WebView reuses keep-alive connections, so replying "Connection: close" to everything
 * makes the JS fetch() reuse a dead socket and hang.
 */
class LocalServer(
    private val assets: AssetManager,
    private val backendHost: String,
    private val backendPort: Int,
    private val toolsHost: String,
    private val toolsPort: Int,
) {
    private val pool = Executors.newCachedThreadPool()
    @Volatile private var serverSocket: ServerSocket? = null

    fun start(onReady: (Int) -> Unit) {
        val ss = ServerSocket(0, 64, InetAddress.getByName("127.0.0.1"))
        serverSocket = ss
        Thread {
            while (!ss.isClosed) {
                val conn = try { ss.accept() } catch (_: Exception) { break }
                pool.execute { handle(conn) }
            }
        }.apply { isDaemon = true }.start()
        Log.i(TAG, "listening on 127.0.0.1:${ss.localPort}")
        onReady(ss.localPort)
    }

    fun stop() {
        runCatching { serverSocket?.close() }
        pool.shutdownNow()
    }

    private fun handle(socket: Socket) {
        socket.use { s ->
            s.tcpNoDelay = true
            val input = s.getInputStream().buffered()
            val out = BufferedOutputStream(s.getOutputStream())
            try {
                while (true) {
                    val requestLine = readLine(input) ?: break
                    val parts = requestLine.split(" ")
                    if (parts.size < 2) break
                    val method = parts[0].uppercase()
                    val path = parts[1]

                    val headers = HashMap<String, String>()
                    while (true) {
                        val line = readLine(input) ?: break
                        if (line.isEmpty()) break
                        val idx = line.indexOf(':')
                        if (idx > 0) {
                            headers[line.substring(0, idx).trim().lowercase()] =
                                line.substring(idx + 1).trim()
                        }
                    }
                    val contentLength = headers["content-length"]?.toIntOrNull() ?: 0
                    val body = if (contentLength > 0) ByteArray(contentLength).also { readFully(input, it) }
                    else ByteArray(0)

                    val keepAlive = route(method, path, headers, body, out)
                    out.flush()
                    if (!keepAlive) break
                }
            } catch (e: Exception) {
                Log.e(TAG, "handle error", e)
            }
        }
    }

    /** Handle one request. Returns true if the connection may be reused. */
    private fun route(
        method: String,
        path: String,
        headers: Map<String, String>,
        body: ByteArray,
        out: OutputStream,
    ): Boolean {
        val clientClose = headers["connection"]?.equals("close", true) == true

        // Local control endpoints (fixed-size JSON -> keep-alive)
        if (path.startsWith("/v1/health")) {
            val status = when {
                NativeLlama.ready -> "ok"
                NativeLlama.loading -> "loading"
                else -> "no-model"
            }
            return writeBytes(out, 200, "OK", "application/json", """{"status":"$status"}""".toByteArray(), !clientClose)
        }
        if (path.startsWith("/v1/models")) {
            val json = """{"object":"list","data":[{"id":"mi9-nexus-v3-Q8_0","object":"model","owned_by":"mi9"}]}"""
            return writeBytes(out, 200, "OK", "application/json", json.toByteArray(), !clientClose)
        }

        // Bundled webapp assets (fixed-size -> keep-alive)
        if (!path.startsWith("/v1/") && !path.startsWith("/tools/")) {
            val name = assetName(path)
            val data = if (name.contains("..")) null
            else runCatching { assets.open(name).use { it.readBytes() } }.getOrNull()
            return if (data != null) {
                writeBytes(out, 200, "OK", mimeFor(name), data, !clientClose)
            } else {
                writeBytes(out, 404, "Not Found", "text/plain; charset=utf-8", "not found".toByteArray(), !clientClose)
            }
        }

        // Local chat completion
        if (path.startsWith("/v1/chat/completions") && method == "POST" && NativeLlama.ready) {
            val stream = runCatching { JSONObject(String(body, Charsets.UTF_8)).optBoolean("stream", false) }
                .getOrDefault(false)
            if (stream) {
                writeHead(out, 200, "OK", "text/event-stream", close = true)
                streamChat(body, out)
                return false
            }
            val json = runCatching { chatCompletion(body) }
                .getOrElse { """{"error":"${it.message?.replace("\"", "'")}"}""" }
            return writeBytes(out, 200, "OK", "application/json", json.toByteArray(), !clientClose)
        }

        // Everything else (/v1 before the model is ready, /tools) -> proxy (streamed, close)
        val isTools = path.startsWith("/tools/")
        val base = when {
            isTools && AlpineSetup.toolServerUp -> "http://127.0.0.1:${AlpineSetup.TOOL_PORT}"
            isTools -> "http://$toolsHost:$toolsPort"
            else -> "http://$backendHost:$backendPort"
        }
        // The tool server exposes /run_python etc. at its root; strip the /tools prefix.
        val proxiedPath = if (isTools) path.removePrefix("/tools") else path
        proxy(method, proxiedPath, headers, body, out, base)
        return false
    }

    // ---- response writers -------------------------------------------------

    /** Write a fixed-size response. Returns whether the connection can be reused. */
    private fun writeBytes(
        out: OutputStream, code: Int, reason: String, mime: String, data: ByteArray, keepAlive: Boolean,
    ): Boolean {
        val sb = StringBuilder()
        sb.append("HTTP/1.1 ").append(code).append(' ').append(reason).append("\r\n")
        sb.append("Content-Type: ").append(mime).append("\r\n")
        sb.append("Content-Length: ").append(data.size).append("\r\n")
        sb.append("Connection: ").append(if (keepAlive) "keep-alive" else "close").append("\r\n\r\n")
        out.write(sb.toString().toByteArray())
        out.write(data)
        out.flush()
        return keepAlive
    }

    /** Write a status line + headers (no body). Caller streams the body. */
    private fun writeHead(out: OutputStream, code: Int, reason: String, mime: String, close: Boolean) {
        val sb = StringBuilder()
        sb.append("HTTP/1.1 ").append(code).append(' ').append(reason).append("\r\n")
        sb.append("Content-Type: ").append(mime).append("\r\n")
        sb.append("Connection: ").append(if (close) "close" else "keep-alive").append("\r\n\r\n")
        out.write(sb.toString().toByteArray())
        out.flush()
    }

    // ---- chat (local) -----------------------------------------------------

    private data class ChatRequest(val system: String?, val user: String, val maxTokens: Int)

    /**
     * Parse an OpenAI-style body into (system, user, maxTokens). Honors
     * chat_template_kwargs.enable_thinking: when false, append Qwen3's "/no_think"
     * marker to the user turn (the legacy chat-template path can't take jinja kwargs).
     */
    private fun parseChat(body: ByteArray): ChatRequest? {
        val req = JSONObject(String(body, Charsets.UTF_8))
        val messages = req.optJSONArray("messages") ?: return null
        val maxTokens = req.optInt("max_tokens", 512)
        val enableThinking = req.optJSONObject("chat_template_kwargs")
            ?.optBoolean("enable_thinking", true) ?: true

        var system: String? = null
        var lastUser: String? = null
        for (i in 0 until messages.length()) {
            val m = messages.optJSONObject(i) ?: continue
            when (m.optString("role")) {
                "system" -> system = m.optString("content")
                "user" -> lastUser = m.optString("content")
            }
        }
        val user = lastUser ?: return null
        val finalUser = if (enableThinking) user else "$user\n/no_think"
        return ChatRequest(system, finalUser, maxTokens)
    }

    private fun chatCompletion(body: ByteArray): String {
        val cr = parseChat(body) ?: error("no user message")
        val rc = NativeLlama.processSystemPrompt(cr.system ?: "") +
            NativeLlama.processUserPrompt(cr.user, cr.maxTokens)
        check(rc == 0) { "llama process failed: $rc" }

        val sb = StringBuilder()
        while (true) {
            val tok = NativeLlama.generateNextToken() ?: break
            sb.append(tok)
        }
        val content = JSONObject.quote(sb.toString())
        return """{"id":"chatcmpl-local","object":"chat.completion","model":"mi9-nexus-v3-Q8_0","choices":[{"index":0,"message":{"role":"assistant","content":$content},"finish_reason":"stop"}]}"""
    }

    /** Stream a chat completion as SSE (writeHead already sent). */
    private fun streamChat(body: ByteArray, out: OutputStream) {
        try {
            val cr = parseChat(body)
            if (cr != null) {
                val rc = NativeLlama.processSystemPrompt(cr.system ?: "") +
                    NativeLlama.processUserPrompt(cr.user, cr.maxTokens)
                if (rc == 0) {
                    while (true) {
                        val tok = NativeLlama.generateNextToken() ?: break
                        if (tok.isEmpty()) continue
                        val delta = """{"choices":[{"delta":{"content":${JSONObject.quote(tok)}}}]}"""
                        out.write(("data: $delta\n\n").toByteArray())
                        out.flush()
                    }
                }
            }
            out.write("data: [DONE]\n\n".toByteArray())
            out.flush()
        } catch (e: Exception) {
            runCatching {
                val msg = e.message?.replace("\"", "'") ?: "error"
                out.write(("data: {\"error\":\"$msg\"}\n\n").toByteArray())
                out.write("data: [DONE]\n\n".toByteArray())
                out.flush()
            }
        }
    }

    // ---- proxy ------------------------------------------------------------

    private fun proxy(
        method: String, path: String, headers: Map<String, String>,
        body: ByteArray, out: OutputStream, base: String,
    ) {
        var conn: HttpURLConnection? = null
        try {
            val url = URL("$base$path")
            conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = method
                connectTimeout = 5_000
                readTimeout = 180_000
                doInput = true
                headers.forEach { (k, v) -> if (!hopByHop(k)) setRequestProperty(k, v) }
                if (body.isNotEmpty()) {
                    doOutput = true
                    outputStream.use { it.write(body) }
                }
            }
            val code = conn!!.responseCode
            val reason = conn!!.responseMessage
            val mime = conn!!.contentType ?: "application/json"
            writeHead(out, code, reason, mime, close = true)
            val stream = if (code in 200..299) conn!!.inputStream else conn!!.errorStream
            if (stream != null) stream.copyTo(out)
        } catch (e: Exception) {
            val msg = e.message?.replace("\"", "'") ?: "unknown error"
            runCatching {
                writeHead(out, 503, "Service Unavailable", "application/json", close = true)
                out.write("""{"error":"backend unreachable: $msg"}""".toByteArray())
                out.flush()
            }
        } finally {
            runCatching { conn?.disconnect() }
        }
    }

    private fun hopByHop(name: String): Boolean {
        return name == "host" || name == "content-length" || name == "connection" ||
            name == "transfer-encoding" || name == "keep-alive" || name == "upgrade"
    }

    // ---- helpers ----------------------------------------------------------

    private fun assetName(path: String): String {
        var name = path.removePrefix("/")
        if (name.isEmpty()) name = "webapp/index.html"
        return name.replace('\\', '/')
    }

    private fun readLine(input: InputStream): String? {
        val sb = StringBuilder()
        while (true) {
            val b = input.read()
            if (b < 0) return if (sb.isEmpty()) null else sb.toString()
            if (b == '\n'.code) break
            if (b != '\r'.code) sb.append(b.toChar())
        }
        return sb.toString()
    }

    private fun readFully(input: InputStream, buf: ByteArray) {
        var off = 0
        while (off < buf.size) {
            val n = input.read(buf, 0, buf.size - off)
            if (n < 0) break
            off += n
        }
    }

    private fun mimeFor(name: String): String = when (name.substringAfterLast('.', "").lowercase()) {
        "html", "htm" -> "text/html; charset=utf-8"
        "js", "mjs" -> "application/javascript; charset=utf-8"
        "css" -> "text/css; charset=utf-8"
        "json" -> "application/json"
        "svg" -> "image/svg+xml"
        "png" -> "image/png"
        "jpg", "jpeg" -> "image/jpeg"
        "webp" -> "image/webp"
        "gif" -> "image/gif"
        "woff" -> "font/woff"
        "woff2" -> "font/woff2"
        "ttf" -> "font/ttf"
        "ico" -> "image/x-icon"
        else -> "application/octet-stream"
    }

    private companion object {
        const val TAG = "Mi9Server"
    }
}