package com.couchbase.lite.mobiletest.util;


import androidx.annotation.NonNull;

import java.io.PrintStream;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Collections;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.mobiletest.services.Log;


public final class DefaultLogger extends Log.TestLogger {
    private static final int THREAD_FIELD_LEN = 7;
    private static final String THREAD_FIELD_PAD = String.join("", Collections.nCopies(THREAD_FIELD_LEN, " "));
    private static final ThreadLocal<DateTimeFormatter> TS_FORMAT
        = ThreadLocal.withInitial(() -> DateTimeFormatter.ofPattern("MM-dd HH:mm:ss.SSS"));

    public DefaultLogger(@NonNull LogLevel level) {
        super(level);
    }

    // These are messages from the Test Server: log them to the console
    @Override
    public void writeLog(LogLevel level, String tag, String msg, Exception err) {
        final PrintStream logStream = (LogLevel.WARNING.compareTo(level) >= 0) ? System.err : System.out;
        logStream.println(formatLog(tag, msg));
        if (err != null) { err.printStackTrace(logStream); }
    }

    @Override
    protected void writeLog(@NonNull LogLevel level, @NonNull LogDomain domain, @NonNull String message) {
        // these CBL messages have already been sent to the console
    }

    public void close() {
        // no-op
    }


    @NonNull
    private String formatLog(@NonNull String tag, @NonNull String message) {
        final String tf = THREAD_FIELD_PAD + Thread.currentThread().getId();
        return TS_FORMAT.get().format(LocalDateTime.now())
            + tf.substring(tf.length() - THREAD_FIELD_LEN)
            + LOG_PREFIX + tag + ": " + message;
    }
}
