package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.Arrays;
import java.util.concurrent.atomic.AtomicReference;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.logging.LogSinks;
import com.couchbase.lite.logging.ConsoleLogSink;
import com.couchbase.lite.logging.BaseLogSink;
import com.couchbase.lite.mobiletest.util.DefaultLogger;


public final class Log {
    private Log() { }

    private static final String TAG = "LOG";

    /**
     * A CustomLogger that can be used to log messages from this test server.
     */
    public abstract static class TestLogger extends BaseLogSink implements AutoCloseable {
        public static final String LOG_PREFIX = " CBLTEST/";

        public TestLogger(@NonNull LogLevel level, @NonNull LogDomain... domains) {
            super(level, Arrays.asList(domains));
        }

        // Log callback: only receives messages at specified level/domains
        @Override
        public abstract void writeLog(@NonNull LogLevel level, @NonNull LogDomain domain, @NonNull String message);

        public void log(LogLevel level, String tag, String msg) {
            writeLog(level, LogDomain.DATABASE, LOG_PREFIX + tag + ": " + msg);
        }

        public void log(LogLevel level, String tag, String msg, Exception err) {
            String fullMsg = LOG_PREFIX + tag + ": " + msg + (err != null ? (" [exception: " + err.getMessage() + "]") : "");
            writeLog(level, LogDomain.DATABASE, fullMsg);
        }

        // does not throw
        public abstract void close();
    }

    private static final AtomicReference<TestLogger> LOGGER = new AtomicReference<>();

    public static void init() {
        // Install a new console log sink
        LogSinks.get().setConsole(new ConsoleLogSink(LogLevel.DEBUG, LogDomain.ALL_DOMAINS));
        installDefaultLogger();
        p(TAG, "Logging initialized");
    }

    public static void p(String tag, String msg) {
        log(LogLevel.INFO, tag, msg, null);
    }

    public static void err(String tag, String msg) {
        log(LogLevel.ERROR, tag, msg, null);
    }

    public static void err(String tag, String msg, Exception err) {
        log(LogLevel.ERROR, tag, msg, err);
    }

    private static void log(
            @NonNull LogLevel level,
            @NonNull String tag,
            @NonNull String msg,
            @Nullable Exception err
    ) {
        TestLogger logger = LOGGER.get();
        if (logger != null) {
            logger.log(level, tag, msg, err);
        }
    }

    public static void installDefaultLogger() {
        installLogger(new DefaultLogger(LogLevel.DEBUG, LogDomain.DATABASE));
    }

    public static void installRemoteLogger(@NonNull String url, @NonNull String sessionId, @NonNull String tag) {
        err(TAG, "Remote logging not yet supported");
        installLogger(new RemoteLogger(url, sessionId, tag, LogLevel.DEBUG, LogDomain.DATABASE));
    }

    private static void installLogger(@NonNull TestLogger logger) {
        TestLogger oldLogger = LOGGER.getAndSet(logger);
        LogSinks.get().setCustom(logger);
        if (oldLogger != null) {
            oldLogger.close();
        }
    }
}
