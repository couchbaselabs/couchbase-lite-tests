package com.couchbase.lite.testserver

class TestServer() {
    companion object {
        init {
            System.loadLibrary("testserver")
        }

        fun initFilesContext(filesDir: String, tempDir: String, assetsDir: String) {
            initAndroidContext(filesDir, tempDir, assetsDir);
        }
    }

    private val server: Long

    init {
        server = createServer()
    }

    fun start() {
        start(server)
    }

    fun stop() {
        stop(server)
    }

    protected fun finalize() {
        stop()
        free(server)
    }

    private external fun createServer(): Long

    private external fun start(server: Long)

    private external fun stop(server: Long)

    private external fun free(server: Long)
}

external fun initAndroidContext(filesDir: String, tempDir: String, assetsDir: String)