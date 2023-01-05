package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.annotation.VisibleForTesting;

import java.io.IOException;
import java.io.InputStream;
import java.util.Map;

import com.couchbase.lite.mobiletest.json.Json;


public final class Task extends ObjectStore {
    private static final String TAG = "ARGS";

    @NonNull
    public static Task from(int version, @NonNull InputStream json) throws IOException {
        return new Task(Json.getParser(version).parseTask(json));
    }

    @VisibleForTesting
    Task(@Nullable Map<String, Object> args) { super(args); }
}
