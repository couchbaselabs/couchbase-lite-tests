package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.VisibleForTesting;

import java.io.IOException;
import java.io.InputStream;
import java.util.Map;

import com.couchbase.lite.mobiletest.util.Json;


public final class Args extends ObjectStore {
    private static final String TAG = "ARGS";

    @NonNull
    public static Args parse(@NonNull InputStream json) throws IOException {
        return new Args(new Json().parse(json, Map.class));
    }

    @VisibleForTesting
    @SuppressWarnings("unchecked")
    Args(@Nullable Map<?, ?> args) { super((Map<String, Object>) args); }
}
