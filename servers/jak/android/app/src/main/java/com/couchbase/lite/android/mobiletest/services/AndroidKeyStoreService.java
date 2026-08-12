package com.couchbase.lite.android.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.security.GeneralSecurityException;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.KeyStoreUtils;
import com.couchbase.lite.TLSIdentity;
import com.couchbase.lite.mobiletest.services.KeyStoreService;

public class AndroidKeyStoreService extends KeyStoreService {

    @NonNull
    @Override
    public TLSIdentity getTLSIdentity(
        @NonNull String alias,
        @Nullable String encoding,
        @Nullable byte[] data,
        @Nullable char[] password)
        throws CouchbaseLiteException {
        if (encoding == null || data == null || password == null) {
            final TLSIdentity identity = TLSIdentity.getIdentity(alias);
            if (identity == null) { throw new CouchbaseLiteException("No existing TLS identity found for: " + alias); }
            return identity;
        }
        try (ByteArrayInputStream in = new ByteArrayInputStream(data)) {
            KeyStoreUtils.importEntry(encoding, in, password, "cbltest", password, alias);
        }
        catch (GeneralSecurityException | IOException e) {
            throw new CouchbaseLiteException("Failed to import TLS identity", e);
        }
        catch (Exception e) {
            throw new CouchbaseLiteException("Failed to import TLS identity: " + e.getMessage());
        }
        final TLSIdentity identity = TLSIdentity.getIdentity(alias);
        if (identity == null) { throw new CouchbaseLiteException("Failed to create TLS identity"); }
        return identity;
    }
}