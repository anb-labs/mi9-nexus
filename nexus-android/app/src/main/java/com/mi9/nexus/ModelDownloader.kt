package com.mi9.nexus

import android.content.Context
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * Downloads the Mi9-Nexus GGUF from HuggingFace with progress + resume.
 *
 * The file is ~1.8 GB, so downloads must be resumable (mobile connections drop). If a
 * partial file exists it sends a Range request and appends; otherwise it restarts.
 */
object ModelDownloader {

    // Direct download URL for the GGUF (Cloudflare R2 public bucket).
    const val MODEL_URL = "https://pub-d33de59ed2ce4360adf02fc3e0cd87d6.r2.dev/mi9-nexus-v3-Q8_0.gguf"

    data class Progress(val downloaded: Long, val total: Long) {
        val fraction: Float get() = if (total > 0) (downloaded.toFloat() / total).coerceIn(0f, 1f) else 0f
    }

    fun file(context: Context): File = File(context.filesDir, "model.gguf")

    fun isComplete(context: Context): Boolean {
        val f = file(context)
        return f.exists() && f.length() > 1_000_000_000L // > ~1 GB sanity check
    }

    /**
     * Download [MODEL_URL] to filesDir/model.gguf, resuming if partially present.
     * Returns the file on success.
     */
    fun download(context: Context, onProgress: (Progress) -> Unit): Result<File> = runCatching {
        val dest = file(context)
        var attempt = 0
        while (true) {
            val existing = if (dest.exists()) dest.length() else 0L
            val conn = (URL(MODEL_URL).openConnection() as HttpURLConnection).apply {
                connectTimeout = 15_000
                readTimeout = 60_000
                setRequestProperty("User-Agent", "Mi9-Nexus")
                if (existing > 0) setRequestProperty("Range", "bytes=$existing-")
            }
            val code = conn.responseCode
            val resuming = code == 206
            val total = if (resuming) existing + conn.contentLengthLong else conn.contentLengthLong
            val startOffset = if (resuming) existing else 0L
            if (total > 0) onProgress(Progress(startOffset, total))

            FileOutputStream(dest, resuming).use { output ->
                conn.inputStream.use { input ->
                    val buf = ByteArray(1 shl 16)
                    var done = startOffset
                    while (true) {
                        val n = input.read(buf)
                        if (n < 0) break
                        output.write(buf, 0, n)
                        done += n
                        onProgress(Progress(done, total))
                    }
                }
            }

            val size = dest.length()
            if (total <= 0 || size >= total) {
                Log.i(TAG, "model downloaded: $size bytes")
                return@runCatching dest
            }
            // Incomplete (connection dropped) -> retry, resuming from current size.
            Log.w(TAG, "download incomplete ($size/$total), retry $attempt")
            if (++attempt > 4) error("download failed after $attempt attempts ($size/$total)")
        }
        dest
    }

    private const val TAG = "Mi9Model"
}