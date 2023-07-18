package com.couchbase.lite.mobiletest.util;

public final class Log {
    private static final String LOG_PREFIX = "CBLTEST/";


    private Log() { }

    public static void d(String tag, String msg) { android.util.Log.d(LOG_PREFIX + tag, msg); }

    public static void i(String tag, String msg) { android.util.Log.i(LOG_PREFIX + tag, msg); }

    public static void w(String tag, String msg) { android.util.Log.w(LOG_PREFIX + tag, msg); }

    public static void w(String tag, String msg, Exception err) { android.util.Log.w(LOG_PREFIX + tag, msg, err); }

    public static void e(String tag, String msg) { android.util.Log.e(LOG_PREFIX + tag, msg); }

    public static void e(String tag, String msg, Exception err) { android.util.Log.e(LOG_PREFIX + tag, msg, err); }
}
