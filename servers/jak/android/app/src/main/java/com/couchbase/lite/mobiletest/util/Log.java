package com.couchbase.lite.mobiletest.util;

public final class Log {
    private Log() {}

    public static void d(String tag, String msg) { android.util.Log.d(tag, msg); }

    public static void i(String tag, String msg) { android.util.Log.i(tag, msg); }

    public static void w(String tag, String msg) { android.util.Log.w(tag, msg); }

    public static void w(String tag, String msg, Exception err) { android.util.Log.w(tag, msg, err); }

    public static void e(String tag, String msg) { android.util.Log.e(tag, msg); }

    public static void e(String tag, String msg, Exception err) { android.util.Log.e(tag, msg, err); }
}
