package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;

import com.couchbase.lite.mobiletest.data.TypedMap;


// Not thread safe...
public final class Memory extends TypedMap {
    @NonNull
    private final String client;

    Memory(@NonNull String client) { this.client = client; }

    @NonNull
    public String getClient() { return client; }
}
