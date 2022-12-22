package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.squareup.moshi.JsonReader;
import com.squareup.moshi.Moshi;
import okio.Okio;

import com.couchbase.lite.mobiletest.util.Log;


public final class Args extends ObjectStore {
    private static final String TAG = "ARGS";

    private static final Moshi PARSER = new Moshi.Builder().build();

    @NonNull
    public static Args parse(@Nullable String json, @NonNull Memory mem) { return new Args(deserializeMap(json, mem)); }

    @NonNull
    private static Map<String, Object> deserializeMap(@Nullable String json, @NonNull Memory mem) {
        final Map<String, Object> map = new HashMap<>();
        if (json == null) { return map; }

        Map<?, ?> parsedJson = null;
        try { parsedJson = PARSER.adapter(Map.class).fromJson(json); }
        catch (IOException e) { Log.w(TAG, "Failed parsing args: " + json, e); }
        if (parsedJson == null) { return map; }

        for (Map.Entry<?, ?> entry: parsedJson.entrySet()) {
            final Object k = entry.getKey();
            final Object v = entry.getValue();
            if (!((k instanceof String) && (v instanceof String))) {
                Log.w(TAG, "Unexpected types in map: " + k.getClass() + " => " + v.getClass() + ": " + k + " => " + v);
                continue;
            }
            map.put((String) k, deserialize((String) v, mem));
        }

        return map;
    }

    @NonNull
    private static List<Object> deserializeList(@Nullable String json, @NonNull Memory mem) {
        final List<Object> list = new ArrayList<>();
        if (json == null) { return list; }

        List<?> parsedJson = null;
        try { parsedJson = PARSER.adapter(List.class).fromJson(json); }
        catch (IOException e) { Log.w(TAG, "Failed parsing args: " + json, e); }
        if (parsedJson == null) { return list; }

        for (Object i: parsedJson) {
            if (!(i instanceof String)) {
                Log.w(TAG, "Unexpected types in list: " + i.getClass() + ": " + i);
                continue;
            }
            list.add(deserialize((String) i, mem));
        }

        return list;
    }

    @SuppressWarnings("PMD.NPathComplexity")
    @Nullable
    private static Object deserialize(@Nullable String value, @NonNull Memory mem) {
        if ((null == value) || ("null".equals(value))) { return null; }
        if (value.startsWith("@")) { return mem.get(value, Object.class); }
        if ("true".equals(value)) { return Boolean.TRUE; }
        if ("false".equals(value)) { return Boolean.FALSE; }
        if (value.startsWith("\"") && value.endsWith("\"")) { return value.substring(1, value.length() - 1); }
        switch (value.substring(0, 1)) {
            case "I":
                return Integer.valueOf(1);
            case "L":
                return Long.valueOf(1);
            case "F":
            case "D":
                return Double.valueOf(1);
            case "[":
                return deserializeList(value, mem);
            case "{":
                return deserializeMap(value, mem);
            default:
                throw new IllegalArgumentException("Unrecognized value in deserializer: " + value);
        }
    }

    private Args(@NonNull Map<String, Object> args) { super(args); }
}
