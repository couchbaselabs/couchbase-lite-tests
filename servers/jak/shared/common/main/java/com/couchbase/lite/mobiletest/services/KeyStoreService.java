package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.TLSIdentity;

public abstract class KeyStoreService {

    @NonNull
    public abstract TLSIdentity getTLSIdentity(
        @NonNull String alias,
        @Nullable String encoding,
        @Nullable byte[] data,
        @Nullable char[] password)
        throws CouchbaseLiteException;
}