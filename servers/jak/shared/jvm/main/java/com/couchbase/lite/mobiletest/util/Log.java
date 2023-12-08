package com.couchbase.lite.mobiletest.util;


import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.io.PrintStream;
import java.io.UnsupportedEncodingException;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Collections;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.Logger;
import com.couchbase.lite.mobiletest.errors.ServerError;


public final class Log {
    private static final int THREAD_FIELD_LEN = 7;
    private static final String THREAD_FIELD_PAD = String.join("", Collections.nCopies(THREAD_FIELD_LEN, " "));
    private static final ThreadLocal<DateTimeFormatter> TS_FORMAT
        = ThreadLocal.withInitial(() -> DateTimeFormatter.ofPattern("MM-dd HH:mm:ss.SSS"));

    public static class CustomLogger implements Logger {
        @NonNull
        @Override
        public LogLevel getLevel() { return LogLevel.DEBUG; }

        @Override
        public void log(@NonNull LogLevel level, @NonNull LogDomain domain, @NonNull String msg) {
            withLog(log -> log.logInternal(level.toString(), "CouchbaseLite", domain.toString(), msg, null));
        }
    }

    private static final AtomicReference<Log> LOGGER = new AtomicReference<>(new Log(System.out));

    @SuppressWarnings("PMD.CloseResource")
    public static void setLogger(@Nullable String testName) {
        final Log oldLogger = LOGGER.getAndSet(new Log((testName == null) ? System.out : openLogFile(testName)));
        if (oldLogger != null) { oldLogger.close(); }
    }

    public static void p(@NonNull String tag, @NonNull String msg) {
        withLog(log -> log.logInternal("I", "TestServer", tag, msg, null));
    }

    // ??? shouldn't these two methods be replaced with a thrown exception?
    public static void err(@NonNull String tag, @NonNull String msg) { err(tag, msg, null); }

    @SuppressWarnings("PMD.AvoidPrintStackTrace")
    public static void err(@NonNull String tag, @NonNull String msg, @Nullable Throwable err) {
        withLog(log -> log.logInternal("E", "TestServer", tag, msg, err));
    }

    @SuppressWarnings({"RegexpSinglelineJava", "PMD.SystemPrintln"})
    private static void withLog(@NonNull Consumer<Log> task) {
        final Log log = LOGGER.get();
        if (log == null) {
            System.err.println("No logger!");
            return;
        }
        task.accept(log);
    }

    @NonNull
    private static PrintStream openLogFile(@Nullable String logFileName) {
        File logDir = new File(Paths.get("").toAbsolutePath().toString(), "logs");
        try { logDir = logDir.getCanonicalFile(); }
        catch (IOException e) { throw new ServerError("Cannot open log file: " + logDir, e); }

        if (!((logDir.exists() && logDir.isDirectory()) || logDir.mkdirs())) {
            throw new ServerError("Could not create log directory: " + logDir);
        }

        final File logFile = new File(logDir, logFileName + ".log");

        final OutputStream outputStream;
        try { outputStream = new FileOutputStream(logFile, true); }
        catch (FileNotFoundException e) { throw new ServerError("Could not create log file: " + logFile, e); }

        try { return new PrintStream(outputStream, true, "UTF-8"); }
        catch (UnsupportedEncodingException e) { throw new ServerError("UTF-8 not supported", e); }
    }


    @NonNull
    private final PrintStream logStream;

    private Log(@NonNull PrintStream logStream) { this.logStream = logStream; }

    private void close() {
        if ((logStream != System.out) && (logStream != System.err)) { logStream.close(); }
    }

    private void logInternal(
        @NonNull String level,
        @NonNull String src,
        @NonNull String tag,
        @NonNull String message,
        @Nullable Throwable err) {
        logStream.println(formatLog(level, src, tag, message));
        if (err != null) { err.printStackTrace(logStream); }
    }

    @NonNull
    private String formatLog(@NonNull String level, @NonNull String src, @NonNull String tag, @NonNull String message) {
        final String tf = THREAD_FIELD_PAD + Thread.currentThread().getId();
        return TS_FORMAT.get().format(LocalDateTime.now())
            + tf.substring(tf.length() - THREAD_FIELD_LEN)
            + " " + level + "/" + src + "/" + tag + ": " + message;
    }
}
