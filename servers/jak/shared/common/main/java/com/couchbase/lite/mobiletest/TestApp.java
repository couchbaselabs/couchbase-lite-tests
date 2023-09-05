//
// Copyright (c) 2022 Couchbase, Inc All rights reserved.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.security.cert.Certificate;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Calendar;
import java.util.Collections;
import java.util.Date;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import com.couchbase.lite.Database;
import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.TLSIdentity;
import com.couchbase.lite.internal.core.CBLVersion;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.ReplicatorService;
import com.couchbase.lite.mobiletest.util.StringUtils;


@SuppressWarnings("resource")
public abstract class TestApp {
    public static final String HEADER_PROTOCOL_VERSION = "CBLTest-API-Version".toLowerCase(Locale.getDefault());
    public static final int LATEST_SUPPORTED_PROTOCOL_VERSION = 1;
    public static final List<Integer> KNOWN_VERSIONS
        = Collections.unmodifiableList(Arrays.asList(LATEST_SUPPORTED_PROTOCOL_VERSION));

    public static final String HEADER_CLIENT = "CBLTest-Client-ID".toLowerCase(Locale.getDefault());
    public static final String HEADER_SERVER = "CBLTest-Server-ID";

    public static final String KEY_SERVER_VERSION = "version";
    public static final String KEY_API = "apiVersion";
    public static final String KEY_CBL = "cbl";
    public static final String KEY_DEVICE = "device";
    public static final String KEY_DEVICE_MODEL = "model";
    public static final String KEY_DEVICE_SYS_NAME = "systemName";
    public static final String KEY_DEVICE_SYS_VERSION = "systemVersion";
    public static final String KEY_DEVICE_SYS_API = "systemApiVersion";
    public static final String KEY_ADDITIONAL_INFO = "additionalInfo";

    private static final AtomicReference<TestApp> APP = new AtomicReference<>();
    private static final AtomicReference<String> APP_ID = new AtomicReference<>();

    public static void init(@NonNull TestApp app) {
        if (!APP.compareAndSet(null, app)) {
            throw new ServerError("Attempt to re-initialize the Test App");
        }
        app.init();
    }

    @NonNull
    public static TestApp getApp() {
        final TestApp app = APP.get();
        if (app == null) { throw new ServerError("Test App has not been initialized"); }
        return app;
    }


    private final Map<String, TestContext> testContexts = new HashMap<>();

    private final AtomicReference<DatabaseService> dbSvc = new AtomicReference<>();
    private final AtomicReference<ReplicatorService> replSvc = new AtomicReference<>();

    protected abstract void initCBL();

    @NonNull
    public abstract String getPlatform();

    @NonNull
    public abstract Map<String, Object> getSystemInfo();

    @NonNull
    public abstract String encodeBase64(@NonNull byte[] hashBytes);

    @NonNull
    public abstract byte[] decodeBase64(@NonNull String encodedBytes);

    @NonNull
    public abstract InputStream getAsset(@NonNull String name) throws IOException;

    @NonNull
    public abstract File getFilesDir();

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @NonNull
    public abstract TLSIdentity getCreateIdentity() throws Exception;

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @NonNull
    public abstract TLSIdentity getSelfSignedIdentity() throws Exception;

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @NonNull
    public abstract TLSIdentity getClientCertsIdentity() throws Exception;

    @NonNull
    public final String getAppId() { return APP_ID.get(); }

    @NonNull
    public final String getAppVersion() {
        return "Test Server (" + getPlatform() + ") :: " + CBLVersion.getVersionInfo();
    }

    @NonNull
    public final List<Certificate> getAuthenticatorCertsList() throws CertificateException, IOException {
        final CertificateFactory certFactory = CertificateFactory.getInstance("X.509");

        final List<Certificate> certsList = new ArrayList<>();
        try (InputStream cert = getAsset("client.p12")) {
            certsList.add(certFactory.generateCertificate(cert));
        }

        return certsList;
    }

    @NonNull
    public final TestContext getTestContext(@NonNull String client) {
        TestContext ctxt = testContexts.get(client);
        if (ctxt != null) { return ctxt; }

        ctxt = new TestContext(client);
        testContexts.put(client, ctxt);

        return ctxt;
    }

    @NonNull
    public final TestContext resetContext(@NonNull String client) {
        testContexts.remove(client);
        return getTestContext(client);
    }

    @NonNull
    public final DatabaseService getDbSvc() {
        final DatabaseService mgr = dbSvc.get();
        if (mgr == null) { dbSvc.compareAndSet(null, new DatabaseService()); }
        return dbSvc.get();
    }

    @Nullable
    public final DatabaseService clearDbSvc() { return dbSvc.getAndSet(null); }

    @NonNull
    public final ReplicatorService getReplSvc() {
        final ReplicatorService mgr = replSvc.get();
        if (mgr == null) { replSvc.compareAndSet(null, new ReplicatorService()); }
        return replSvc.get();
    }

    @Nullable
    public final ReplicatorService clearReplSvc() { return replSvc.getAndSet(null); }

    @NonNull
    protected final Date getExpirationTime() {
        final Calendar calendar = Calendar.getInstance();
        calendar.add(Calendar.YEAR, 2);
        return calendar.getTime();
    }

    @NonNull
    protected final Map<String, String> getX509Attributes() {
        final Map<String, String> attributes = new HashMap<>();
        attributes.put(TLSIdentity.CERT_ATTRIBUTE_COMMON_NAME, "CBL Test");
        attributes.put(TLSIdentity.CERT_ATTRIBUTE_ORGANIZATION, "Couchbase");
        attributes.put(TLSIdentity.CERT_ATTRIBUTE_ORGANIZATION_UNIT, "Mobile");
        attributes.put(TLSIdentity.CERT_ATTRIBUTE_EMAIL_ADDRESS, "lite@couchbase.com");
        return attributes;
    }

    private void init() {
        APP_ID.set(StringUtils.randomString(26));

        initCBL();

        Database.log.getConsole().setLevel(LogLevel.DEBUG);
        Database.log.getConsole().setDomains(LogDomain.ALL_DOMAINS);
    }
}
