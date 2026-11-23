package com.mi9.nexus

/**
 * JNI binding to the bundled llama.cpp (libmi9llama.so).
 *
 * The native side (app/src/main/cpp/mi9_llama.cpp) is the llama.cpp Android example
 * wrapper, renamed into the Mi9 namespace. It loads the GGUF model and drives a
 * stateful completion loop: processSystemPrompt -> processUserPrompt -> generateNextToken*.
 */
object NativeLlama {

    external fun init(nativeLibDir: String)
    external fun load(modelPath: String): Int
    external fun prepare(): Int
    external fun processSystemPrompt(systemPrompt: String): Int
    external fun processUserPrompt(userPrompt: String, nPredict: Int): Int
    external fun generateNextToken(): String?
    external fun unload()
    external fun shutdown()
    external fun systemInfo(): String

    @Volatile
    var ready = false
        private set

    @Volatile
    var loading = false
        private set

    /** Load the native lib + model once. Returns true on success. */
    fun bootstrap(nativeLibDir: String, modelPath: String): Boolean {
        if (ready) return true
        if (loading) return false
        loading = true
        return try {
            System.loadLibrary("mi9llama")
            init(nativeLibDir)
            val r = load(modelPath)
            if (r != 0) {
                android.util.Log.e("NativeLlama", "llama_model_load failed: $r")
                return false
            }
            val p = prepare()
            if (p != 0) {
                android.util.Log.e("NativeLlama", "prepare failed: $p")
                return false
            }
            ready = true
            android.util.Log.i("NativeLlama", "model ready: ${systemInfo()}")
            true
        } catch (t: Throwable) {
            android.util.Log.e("NativeLlama", "bootstrap failed", t)
            false
        } finally {
            loading = false
        }
    }
}