package com.couchbase.lite.jvm.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.TLSIdentity;
import com.couchbase.lite.mobiletest.services.KeyStoreService;

public class JavaDesktopKeyStoreService extends KeyStoreService {

    private final Map<String, KeyStore> tlsKeyStores = new HashMap<>();
    private final Map<String, char[]> tlsKeyPasswords = new HashMap<>();

    @NonNull
    @Override
    public TLSIdentity getTLSIdentity(
        @NonNull String alias,
        @Nullable String encoding,
        @Nullable byte[] data,
        @Nullable char[] password)
        throws CouchbaseLiteException {
        try {
            if (encoding == null || data == null || password == null) {
                final KeyStore keyStore = tlsKeyStores.get(alias);
                if (keyStore == null) { throw new CouchbaseLiteException("No existing TLS identity found for: " + alias); }
                final TLSIdentity identity = TLSIdentity.getIdentity(keyStore, alias, tlsKeyPasswords.get(alias));
                if (identity == null) { throw new CouchbaseLiteException("Failed to retrieve TLS identity for: " + alias); }
                return identity;
            }

            final KeyStore keyStore = KeyStore.getInstance(encoding);
            try (InputStream in = new ByteArrayInputStream(data)) { keyStore.load(in, password); }
            final KeyStore.ProtectionParameter protParam = new KeyStore.PasswordProtection(password);
            keyStore.setEntry(alias, keyStore.getEntry("cbltest", protParam), protParam);
            final TLSIdentity identity = TLSIdentity.getIdentity(keyStore, alias, password);
            if (identity == null) { throw new CouchbaseLiteException("Failed to create TLS identity"); }

            tlsKeyStores.put(alias, keyStore);
            tlsKeyPasswords.put(alias, password);

            return identity;
        }
        catch (GeneralSecurityException | IOException e) {
            throw new CouchbaseLiteException("Failed to create TLS identity", e);
        }
    }
}