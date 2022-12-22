package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.security.KeyStore;
import java.security.KeyStoreException;
import java.security.NoSuchAlgorithmException;
import java.security.UnrecoverableEntryException;
import java.security.cert.CertificateException;
import java.util.Base64;
import java.util.UUID;

import com.couchbase.lite.CouchbaseLite;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.TLSIdentity;


public abstract class BaseTestApp extends TestApp {
    private final File directory;

    public BaseTestApp() {
        directory = new File(System.getProperty("java.io.tmpdir"), "TestServerTemp");
        if (!(directory.exists() || directory.mkdirs())) {
            throw new IllegalStateException("Cannot create tmp directory: " + directory);
        }
    }

    @Override
    protected void initCBL() { CouchbaseLite.init(true); }

    @NonNull
    @Override
    public File getFilesDir() { return this.directory; }

    @NonNull
    @Override
    public String encodeBase64(@NonNull byte[] hashBytes) { return Base64.getEncoder().encodeToString(hashBytes); }

    @NonNull
    @Override
    public byte[] decodeBase64(@NonNull String encodedBytes) { return Base64.getDecoder().decode(encodedBytes); }

    @Nullable
    @Override
    public InputStream getAsset(@NonNull String name) { return TestApp.class.getResourceAsStream("/" + name); }

    @NonNull
    @Override
    public TLSIdentity getCreateIdentity()
        throws KeyStoreException, CertificateException, IOException, NoSuchAlgorithmException, CouchbaseLiteException {
        final KeyStore externalStore = KeyStore.getInstance("PKCS12");
        externalStore.load(null, null);

        return TLSIdentity.createIdentity(
            true,
            getX509Attributes(),
            getExpirationTime(),
            externalStore,
            UUID.randomUUID().toString(),
            "pass".toCharArray()
        );
    }

    @NonNull
    @Override
    public TLSIdentity getSelfSignedIdentity()
        throws IOException, KeyStoreException, CertificateException, NoSuchAlgorithmException,
        UnrecoverableEntryException, CouchbaseLiteException {
        final char[] pass = "123456".toCharArray();

        try (InputStream serverCert = getAsset("certs.p12")) {
            final KeyStore trustStore = KeyStore.getInstance("PKCS12");
            trustStore.load(null, null);
            trustStore.load(serverCert, pass);

            final KeyStore.ProtectionParameter protParam = new KeyStore.PasswordProtection(pass);
            final KeyStore.Entry newEntry = trustStore.getEntry("testkit", protParam);
            trustStore.setEntry("Servercerts", newEntry, protParam);

            final TLSIdentity identity = TLSIdentity.getIdentity(trustStore, "Servercerts", pass);
            if (identity == null) { throw new CouchbaseLiteException("Identity not found"); }
            return identity;
        }
    }

    @NonNull
    @Override
    public TLSIdentity getClientCertsIdentity()
        throws KeyStoreException, CertificateException, IOException, NoSuchAlgorithmException,
        UnrecoverableEntryException, CouchbaseLiteException {
        final char[] pass = "123456".toCharArray();

        final KeyStore trustStore = KeyStore.getInstance("PKCS12");
        trustStore.load(null, null);

        try (InputStream cert = getAsset("client.p12")) { trustStore.load(cert, pass); }

        final KeyStore.ProtectionParameter protParam = new KeyStore.PasswordProtection(pass);
        trustStore.setEntry("Clientcerts", trustStore.getEntry("testkit", protParam), protParam);

        final TLSIdentity identity = TLSIdentity.getIdentity(trustStore, "Clientcerts", pass);
        if (identity == null) { throw new CouchbaseLiteException("Identity not found"); }
        return identity;
    }
}
