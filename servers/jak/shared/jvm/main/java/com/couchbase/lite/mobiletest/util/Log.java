package com.couchbase.lite.mobiletest.util;


import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Collections;


public final class Log {
    private Log() { }

    private static final String LOG_TAG = "/TestServer/";
    private static final int THREAD_FIELD_LEN = 7;
    private static final String THREAD_FIELD_PAD = String.join("", Collections.nCopies(THREAD_FIELD_LEN, " "));
    private static final ThreadLocal<DateTimeFormatter> TS_FORMAT
        = ThreadLocal.withInitial(() -> DateTimeFormatter.ofPattern("MM-dd HH:mm:ss.SSS"));

    public static void p(@NonNull String tag, @NonNull String msg) { logInternal(false, tag, msg); }

    // ??? shouldn't these be replaced with a thrown exception?
    public static void err(@NonNull String tag, @NonNull String msg) { err(tag, msg, null); }

    @SuppressWarnings("PMD.AvoidPrintStackTrace")
    public static void err(@NonNull String tag, @NonNull String msg, @Nullable Throwable err) {
        logInternal(true, tag, msg);
        if (err != null) { err.printStackTrace(); }
    }

    private static void logInternal(boolean isError, @NonNull String tag, @NonNull String message) {
        ((isError) ? System.out : System.err).println(formatLog((isError) ? "E" : "I", tag, message));
    }

    @NonNull
    private static String formatLog(@NonNull String level, @NonNull String tag, @NonNull String message) {
        final String tf = THREAD_FIELD_PAD + Thread.currentThread().getId();
        return TS_FORMAT.get().format(LocalDateTime.now())
            + tf.substring(tf.length() - THREAD_FIELD_LEN)
            + " " + level + LOG_TAG + tag + ": " + message;
    }
}
