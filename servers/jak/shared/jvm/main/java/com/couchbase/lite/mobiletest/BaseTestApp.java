package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.ByteArrayInputStream;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.io.InputStream;
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.KeyStoreException;
import java.security.NoSuchAlgorithmException;
import java.security.UnrecoverableEntryException;
import java.security.cert.CertificateException;
import java.util.Base64;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import com.couchbase.lite.CouchbaseLite;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.TLSIdentity;
import com.couchbase.lite.internal.core.CBLVersion;
import com.couchbase.lite.mobiletest.errors.ServerError;


/**
 * Code common to JVM test apps.
 */
public abstract class BaseTestApp extends TestApp {
    private final File directory;

    public BaseTestApp(@NonNull String platform) {
        super(platform);
        directory = new File(System.getProperty("java.io.tmpdir"), "TestServerTemp");
        if (!(directory.exists() || directory.mkdirs())) {
            throw new ServerError("Cannot create tmp directory: " + directory);
        }
    }

    @Override
    protected void initCBL() { CouchbaseLite.init(true); }

    @NonNull
    @Override
    public Map<String, Object> getSystemInfo() {
        final Map<String, Object> content = new HashMap<>();
        content.put(KEY_SERVER_VERSION, CBLVersion.VERSION_NAME);
        content.put(KEY_API, LATEST_SUPPORTED_PROTOCOL_VERSION);
        content.put(KEY_CBL, "couchbase-lite-java");

        final Map<String, Object> device = new HashMap<>();
        device.put(KEY_DEVICE_MODEL, System.getProperty("os.arch"));
        device.put(KEY_DEVICE_SYS_NAME, System.getProperty("os.name"));
        device.put(KEY_DEVICE_SYS_VERSION, System.getProperty("os.version"));
        device.put(KEY_DEVICE_SYS_API, System.getProperty("java.version"));
        content.put(KEY_DEVICE, device);

        content.put(
            KEY_ADDITIONAL_INFO,
            platform + " Test Server " + TestServerInfo.SERVER_VERSION + " using " + CBLVersion.getVersionInfo());

        return content;
    }

    @NonNull
    @Override
    public File getFilesDir() { return this.directory; }

    @NonNull
    @Override
    public String encodeBase64(@NonNull byte[] hashBytes) { return Base64.getEncoder().encodeToString(hashBytes); }

    @NonNull
    @Override
    public byte[] decodeBase64(@NonNull String encodedBytes) { return Base64.getDecoder().decode(encodedBytes); }

    @NonNull
    @Override
    public InputStream getAsset(@NonNull String name) throws IOException {
        final InputStream is = TestApp.class.getResourceAsStream("/" + name);
        if (is == null) { throw new FileNotFoundException("No such resource: " + name); }
        return is;
    }

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
            if (identity == null) { throw new ServerError("Identity not found"); }
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
        if (identity == null) { throw new ServerError("Identity not found"); }
        return identity;
    }

    private final Map<String, KeyStore> tlsKeyStores = new HashMap<>();
    private final Map<String, char[]> tlsKeyPasswords = new HashMap<>();

    @NonNull
    @Override
    public TLSIdentity importTlsIdentity(
        @NonNull String alias,
        @NonNull String encoding,
        @NonNull byte[] data,
        @NonNull char[] password)
        throws CouchbaseLiteException {
        try {
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
            throw new CouchbaseLiteException("Failed to import TLS identity", e);
        }
        catch (Exception e) {
            throw new CouchbaseLiteException("Unexpected error importing TLS identity: " + e.getMessage());
        }
    }

    @Nullable
    @Override
    public TLSIdentity getExistingTlsIdentity(@NonNull String alias) throws CouchbaseLiteException {
        final KeyStore keyStore = tlsKeyStores.get(alias);
        if (keyStore == null) { return null; }
        final char[] password = tlsKeyPasswords.get(alias);
        try {
            return TLSIdentity.getIdentity(keyStore, alias, password);
        }
        catch (CouchbaseLiteException e) {
            throw new CouchbaseLiteException("Failed to retrieve existing TLS identity", e);
        }
    }
}