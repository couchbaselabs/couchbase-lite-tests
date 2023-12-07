package com.couchbase.lite.mobiletest.util;

public final class Log {
    private static final String LOG_PREFIX = "CBLTEST/";


    private Log() { }

    public static void p(String tag, String msg) { android.util.Log.i(LOG_PREFIX + tag, msg); }

    // ??? shouldn't this be replaced with a thrown exception?
    public static void err(String tag, String msg) { err(tag, msg, null); }
    public static void err(String tag, String msg, Exception err) { android.util.Log.e(LOG_PREFIX + tag, msg, err); }
}
