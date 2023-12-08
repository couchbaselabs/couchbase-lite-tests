package com.couchbase.lite.mobiletest.util;

import androidx.annotation.NonNull;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.Logger;


public final class Log {
    private static final String LOG_PREFIX = "CBLTEST/";

    public static class CustomLogger implements Logger {
        @NonNull
        @Override
        public LogLevel getLevel() { return LogLevel.NONE; }

        @Override
        public void log(@NonNull LogLevel level, @NonNull LogDomain domain, @NonNull String message) {
            // Doesn't log
        }
    }


    public static void setLogger(String test) {
        // Using logcat
    }


    private Log() { }

    public static void p(String tag, String msg) { android.util.Log.i(LOG_PREFIX + tag, msg); }

    // ??? shouldn't this be replaced with a thrown exception?
    public static void err(String tag, String msg) { err(tag, msg, null); }

    public static void err(String tag, String msg, Exception err) { android.util.Log.e(LOG_PREFIX + tag, msg, err); }
}
