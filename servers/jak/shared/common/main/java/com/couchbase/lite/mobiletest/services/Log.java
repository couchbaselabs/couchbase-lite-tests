package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.concurrent.atomic.AtomicReference;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.logging.BaseLogSink;
import com.couchbase.lite.logging.ConsoleLogSink;
import com.couchbase.lite.logging.LogSinks;
import com.couchbase.lite.mobiletest.util.DefaultLogger;


public final class Log {
    private Log() { }

    private static final String TAG = "LOG";

    /**
     * A CustomLogger that can be used to log messages from this test server.
     */
    public abstract static class TestLogger extends BaseLogSink implements AutoCloseable {
        public static final String LOG_PREFIX = " CBLTEST/";

        public TestLogger(@NonNull LogLevel level) {
            super(level);
        }

        public final void writeLog(LogLevel level, String tag, String msg) { writeLog(level, tag, msg, null); }

        public abstract void writeLog(LogLevel level, String tag, String msg, Exception err);

        // does not throw
        public abstract void close();
    }

    private static final AtomicReference<TestLogger> LOGGER = new AtomicReference<>();


    public static void init() {
        LogSinks.get().setConsole(new ConsoleLogSink(LogLevel.DEBUG, LogDomain.ALL));
        installDefaultLogger();
        p(TAG, "Logging initialized");
    }

    public static void p(String tag, String msg) {
        log(LogLevel.INFO, tag, msg, null);
    }

    public static void err(String tag, String msg) {
        log(LogLevel.ERROR, tag, msg, null);
    }

    // ??? shouldn't this be replaced with a thrown exception?
    public static void err(String tag, String msg, Exception err) { log(LogLevel.ERROR, tag, msg, err); }

    private static void log(
        @NonNull LogLevel level,
        @NonNull String tag,
        @NonNull String msg,
        @Nullable Exception err) {
        LOGGER.get().writeLog(level, tag, msg, err);
    }

    public static void installDefaultLogger() { installLogger(new DefaultLogger(LogLevel.DEBUG)); }

    public static void installRemoteLogger(@NonNull String url, @NonNull String sessionId, @NonNull String tag) {
        Log.err(TAG, "Remote logging not yet supported");
        final RemoteLogger logger = new RemoteLogger(url, sessionId, tag);
        logger.connect();
        installLogger(logger);
    }

    private static void installLogger(@NonNull TestLogger logger) {
        final TestLogger oldLogger = LOGGER.getAndSet(logger);
        LogSinks.get().setCustom(logger);
        if (oldLogger != null) { oldLogger.close(); }
    }
}
