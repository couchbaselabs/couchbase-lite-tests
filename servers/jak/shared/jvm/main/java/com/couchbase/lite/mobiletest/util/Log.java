package com.couchbase.lite.mobiletest.util;


import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;


public final class Log {
    private Log() { }

    private static final String LOG_TAG = "/TestServer/";
    private static final int THREAD_FIELD_LEN = 7;
    private static final String THREAD_FIELD_PAD = String.join("", Collections.nCopies(THREAD_FIELD_LEN, " "));
    private static final ThreadLocal<DateTimeFormatter> TS_FORMAT
        = ThreadLocal.withInitial(() -> DateTimeFormatter.ofPattern("MM-dd HH:mm:ss.SSS"));
    private static final List<String> LOG_LEVELS = Arrays.asList("ERROR", "WARN", "INFO", "DEBUG");

    public static void d(@NonNull String tag, @NonNull String msg) { log(3, tag, msg); }

    public static void i(@NonNull String tag, @NonNull String msg) { log(2, tag, msg); }

    public static void w(@NonNull String tag, @NonNull String msg) { w(tag, msg, null); }

    @SuppressWarnings("PMD.AvoidPrintStackTrace")
    public static void w(@NonNull String tag, @NonNull String msg, @Nullable Throwable err) {
        log(1, tag, msg);
        if (err != null) { err.printStackTrace(); }
    }

    public static void e(@NonNull String tag, @NonNull String msg) { e(tag, msg, null); }

    @SuppressWarnings("PMD.AvoidPrintStackTrace")
    public static void e(@NonNull String tag, @NonNull String msg, @Nullable Throwable err) {
        log(0, tag, msg);
        if (err != null) { err.printStackTrace(); }
    }

    private static void log(int level, @NonNull String tag, @NonNull String message) {
        ((level >= 2) ? System.out : System.err).println(formatLog(level, tag, message));
    }

    @NonNull
    private static String formatLog(int level, @NonNull String tag, @NonNull String message) {
        final String tf = THREAD_FIELD_PAD + Thread.currentThread().getId();
        return TS_FORMAT.get().format(LocalDateTime.now())
            + tf.substring(tf.length() - THREAD_FIELD_LEN)
            + " " + LOG_LEVELS.get(level) + LOG_TAG + tag + ": "
            + message;
    }
}
