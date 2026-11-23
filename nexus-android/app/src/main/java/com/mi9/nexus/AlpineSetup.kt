package com.mi9.nexus

import android.content.Context
import android.os.Build
import android.util.Log
import java.io.File
import java.io.FileOutputStream
import java.io.InputStream
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.file.Files
import java.nio.file.Path
import java.security.MessageDigest
import java.util.zip.GZIPInputStream

/**
 * PRoot + Alpine bootstrap (the Horus / Kai pattern).
 *
 * On first use this downloads a minimal Alpine rootfs, verifies it against the
 * published SHA-256, and extracts it into app-private storage. No root and no host
 * access: PRoot uses ptrace to emulate chroot inside the app sandbox, giving the
 * model a real Linux userland for run_python / shell tools.
 *
 * Layout (app-private, never leaves the sandbox):
 *   filesDir/nexus/alpine   - the Alpine userland
 *   filesDir/nexus/bin      - helper binaries (proot)
 *
 * PRoot delivery: bundle the Android proot binary as jniLibs/<abi>/libproot.so.
 * Android unpacks native libs to applicationInfo.nativeLibraryDir, so we can exec it
 * directly (no download). If it is not bundled yet, [prootBinary] returns null and
 * [ensureReady] reports it instead of pretending to be ready.
 *
 * This module only *prepares* the sandbox. Running tools inside it is Goal 3.
 */
object AlpineSetup {

    private const val ALPINE_VERSION = "3.20"
    private const val RELEASES_BASE =
        "https://dl-cdn.alpinelinux.org/alpine/v$ALPINE_VERSION/releases"

    data class Progress(val stage: String, val fraction: Float)

    fun rootDir(context: Context): File = File(context.filesDir, "nexus/alpine")
    fun binDir(context: Context): File = File(context.filesDir, "nexus/bin")
    fun libDir(context: Context): File = File(context.filesDir, "lib")

    fun isReady(context: Context): Boolean =
        File(rootDir(context), "etc/alpine-release").exists() && prootBinary(context) != null &&
            File(libDir(context), "libtalloc.so.2").exists()

    fun toolchainReady(context: Context): Boolean =
        File(rootDir(context), "usr/bin/python3").exists() &&
            File(rootDir(context), "toolserver/toolserver.py").exists()

    // ---- tool server (Goal 3) -------------------------------------------

    const val TOOL_PORT = 8090

    @Volatile
    var toolServerUp = false
        private set
    private var toolProcess: Process? = null

    /**
     * Prepare the toolchain: install python3 via apk, deploy toolserver.py into the
     * rootfs, and start it (listening on 127.0.0.1:8090, reachable from the app).
     */
    fun setupToolchain(context: Context, onProgress: (String) -> Unit = {}): Result<Unit> = runCatching {
        ensureReady(context)
        val root = rootDir(context)
        runCatching { File(root, "etc/resolv.conf").writeText("nameserver 8.8.8.8\nnameserver 1.1.1.1\n") }
        onProgress("Installing Python…")
        runCommand(context, root, "apk add --no-cache python3 >/dev/null 2>&1; /usr/bin/python3 --version 2>&1")
        onProgress("Deploying tool server…")
        deployToolServer(context)
        startToolServer(context)
        onProgress("Tool server ready")
    }

    private fun deployToolServer(context: Context) {
        val dest = File(rootDir(context), "toolserver/toolserver.py")
        dest.parentFile.mkdirs()
        context.assets.open("toolserver.py").use { input ->
            FileOutputStream(dest).use { input.copyTo(it) }
        }
    }

    /** Start the python tool server inside Alpine; keeps the proot process alive. */
    fun startToolServer(context: Context) {
        if (toolProcess?.isAlive == true) { toolServerUp = true; return }
        val proot = prootBinary(context) ?: return
        val root = rootDir(context)
        val pb = ProcessBuilder(
            proot.absolutePath, "-r", root.absolutePath, "-0",
            "-b", "/proc", "-b", "/dev", "-w", "/",
            "/usr/bin/python3", "/toolserver/toolserver.py",
        )
        pb.environment().apply {
            this["LD_LIBRARY_PATH"] = "${context.applicationInfo.nativeLibraryDir}:${libDir(context)}"
            this["PROOT_LOADER"] = "${libDir(context)}/loader"
            this["TMPDIR"] = "${libDir(context)}/tmp"
            this["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            this["HOME"] = "/root"
        }
        pb.redirectErrorStream(true)
        toolProcess = pb.start()
        Thread {
            runCatching {
                toolProcess?.inputStream?.bufferedReader()?.useLines { lines ->
                    lines.forEach { Log.i("Mi9Tools", it) }
                }
            }
        }.apply { isDaemon = true }.start()
        toolServerUp = true
    }

    fun stopToolServer() {
        runCatching { toolProcess?.destroy() }
        toolProcess = null
        toolServerUp = false
    }

    /** The proot executable to use, or null if it has not been bundled yet. */
    fun prootBinary(context: Context): File? {
        val bundled = File(context.applicationInfo.nativeLibraryDir, "libproot.so")
        if (bundled.exists()) return bundled
        val copied = File(binDir(context), "proot")
        return if (copied.exists()) copied else null
    }

    /**
     * Ensure the sandbox is prepared. Idempotent; returns quickly once ready.
     * Does NOT run automatically - callers decide when to spend the download.
     */
    fun ensureReady(context: Context, onProgress: (Progress) -> Unit = {}): Result<Unit> =
        runCatching {
            onProgress(Progress("Checking sandbox", 0f))
            ensureLibs(context)
            val arch = detectArch()
            val root = rootDir(context)

            if (!File(root, "etc/alpine-release").exists()) {
                val (url, sha) = resolveRootfs(arch)
                val file = download(url, context.cacheDir)
                verifySha256(file, sha)
                onProgress(Progress("Extracting Alpine", 0.6f))
                extractTarGz(file, root)
                file.delete()
            }

            if (prootBinary(context) == null) {
                onProgress(Progress("proot not bundled (add jniLibs/<abi>/libproot.so)", 0.9f))
            }

            onProgress(Progress("Sandbox ready", 1f))
        }

    /** Extract proot's dependencies from assets into filesDir/lib. */
    private fun ensureLibs(context: Context) {
        val dir = libDir(context)
        dir.mkdirs()
        val abi = Build.SUPPORTED_ABIS.firstOrNull().orEmpty()

        // libtalloc.so.2 (soname libtalloc.so.2)
        val talloc = File(dir, "libtalloc.so.2")
        if (!talloc.exists() || talloc.length() == 0L) {
            context.assets.open("proot/$abi/libtalloc.so.2.5.0").use { input ->
                FileOutputStream(talloc).use { input.copyTo(it) }
            }
            talloc.setReadable(true, false)
        }

        // proot's static loader (the guest-ELF interpreter shim)
        val loader = File(dir, "loader")
        if (!loader.exists() || loader.length() == 0L) {
            context.assets.open("proot/$abi/loader").use { input ->
                FileOutputStream(loader).use { input.copyTo(it) }
            }
            loader.setExecutable(true, false)
            loader.setReadable(true, false)
        }
    }

    /**
     * Run [command] inside the Alpine rootfs via proot; returns combined output.
     *
     * proot (libproot.so) + libandroid-shmem.so are in nativeLibraryDir; libtalloc.so.2
     * and the proot loader are in filesDir/lib. LD_LIBRARY_PATH resolves proot's own
     * deps; PROOT_LOADER points at the static loader proot needs to exec guest ELFs.
     */
    fun runCommand(context: Context, root: File, command: String): String {
        val proot = prootBinary(context) ?: error("proot not bundled")
        val nativeDir = context.applicationInfo.nativeLibraryDir
        val libDir = libDir(context)
        File(libDir, "tmp").mkdirs()
        val pb = ProcessBuilder(
            proot.absolutePath,
            "-r", root.absolutePath,
            "-0",
            "-b", "/proc",
            "-b", "/dev",
            "-w", "/root",
            "/bin/sh", "-c", command,
        )
        pb.environment().apply {
            this["LD_LIBRARY_PATH"] = "$nativeDir:$libDir"
            this["PROOT_LOADER"] = "$libDir/loader"
            this["TMPDIR"] = "$libDir/tmp"
            this["HOME"] = "/root"
            this["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
            this["TERM"] = "xterm"
        }
        pb.redirectErrorStream(true)
        val proc = pb.start()
        val output = proc.inputStream.bufferedReader().use { it.readText() }
        proc.waitFor()
        return output
    }

    private fun detectArch(): String {
        val abi = Build.SUPPORTED_ABIS.firstOrNull().orEmpty()
        return when {
            abi.startsWith("arm64") || abi.startsWith("aarch64") -> "aarch64"
            abi.startsWith("x86_64") || abi == "x86" -> "x86_64"
            else -> "armhf"
        }
    }

    /** Fetch the releases directory index and pick the newest minirootfs tarball. */
    private fun resolveRootfs(arch: String): Pair<String, String> {
        val index = fetchString("$RELEASES_BASE/$arch/")
        val re = Regex("alpine-minirootfs-[\\d.]+-" + Regex.escape(arch) + "\\.tar\\.gz")
        val newest = re.findAll(index).map { it.value }.maxByOrNull { it }
            ?: error("no minirootfs tarball found for arch=$arch")
        val url = "$RELEASES_BASE/$arch/$newest"
        val sha = fetchString(url + ".sha256").substringBefore(' ').trim()
        check(sha.isNotEmpty()) { "empty checksum for $newest" }
        return url to sha
    }

    private fun fetchString(url: String): String {
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 30_000
            setRequestProperty("User-Agent", "Mi9-Nexus")
        }
        return conn.inputStream.bufferedReader().use { it.readText() }
    }

    private fun download(url: String, dir: File): File {
        val out = File(dir, url.substringAfterLast('/'))
        val conn = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 60_000
            setRequestProperty("User-Agent", "Mi9-Nexus")
        }
        conn.inputStream.use { input ->
            FileOutputStream(out).use { output -> input.copyTo(output) }
        }
        return out
    }

    private fun verifySha256(file: File, expected: String) {
        val md = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buf = ByteArray(1 shl 16)
            while (true) {
                val read = input.read(buf)
                if (read < 0) break
                md.update(buf, 0, read)
            }
        }
        val actual = md.digest().joinToString("") { "%02x".format(it) }
        check(actual.equals(expected, ignoreCase = true)) {
            "checksum mismatch for ${file.name}: expected $expected, got $actual"
        }
    }

    private fun extractTarGz(file: File, dest: File) {
        dest.mkdirs()
        GZIPInputStream(file.inputStream().buffered()).use { gz ->
            TarExtractor(gz, dest).extractAll()
        }
    }

    /** Minimal ustar reader: regular files, directories, symlinks. */
    private class TarExtractor(input: InputStream, private val dest: File) {
        private val input = input.buffered()
        private val header = ByteArray(512)
        private val scratch = ByteArray(1 shl 16)

        fun extractAll() {
            while (true) {
                if (!readFully(header)) break
                if (header.all { it.toInt() == 0 }) break

                val name = str(header, 0, 100)
                val prefix = str(header, 345, 155)
                val size = octal(header, 124, 12)
                val mode = octal(header, 100, 8)
                val type = header[156].toInt().toChar()
                val link = str(header, 157, 100)

                val full = if (prefix.isNotEmpty() && name.isNotEmpty()) "$prefix/$name" else name
                if (full.isEmpty()) continue
                val out = File(dest, full)

                val isFile = type == '0' || type == '\u0000'
                when {
                    isFile -> {
                        out.parentFile?.mkdirs()
                        FileOutputStream(out).use { copyExact(it, size) }
                        out.setExecutable((mode and 0b001001001L) != 0L)
                    }
                    type == '5' -> out.mkdirs()
                    type == '2' -> {
                        out.parentFile?.mkdirs()
                        runCatching { Files.createSymbolicLink(out.toPath(), Path.of(link)) }
                    }
                }

                if (!isFile) skip(size)
                skip((512 - (size % 512)) % 512)
            }
        }

        private fun copyExact(output: OutputStream, size: Long) {
            var remaining = size
            while (remaining > 0) {
                val want = minOf(remaining, scratch.size.toLong()).toInt()
                val read = input.read(scratch, 0, want)
                if (read < 0) break
                output.write(scratch, 0, read)
                remaining -= read
            }
        }

        private fun skip(n: Long) {
            var remaining = n
            while (remaining > 0) {
                val want = minOf(remaining, scratch.size.toLong()).toInt()
                val read = input.read(scratch, 0, want)
                if (read < 0) break
                remaining -= read
            }
        }

        private fun readFully(buf: ByteArray): Boolean {
            var off = 0
            while (off < buf.size) {
                val read = input.read(buf, 0, buf.size - off)
                if (read < 0) return off == buf.size
                off += read
            }
            return off == buf.size
        }

        private fun str(buf: ByteArray, offset: Int, count: Int): String {
            var end = offset + count
            if (end > buf.size) end = buf.size
            val bytes = buf.copyOfRange(offset, end)
            var nul = bytes.size
            for (i in bytes.indices) if (bytes[i].toInt() == 0) { nul = i; break }
            return String(bytes, 0, nul, Charsets.UTF_8)
        }

        private fun octal(buf: ByteArray, offset: Int, count: Int): Long {
            var value = 0L
            for (i in offset until offset + count) {
                val c = buf[i].toInt().toChar()
                if (c < '0' || c > '9') break
                value = value * 8 + (c - '0').toLong()
            }
            return value
        }
    }
}