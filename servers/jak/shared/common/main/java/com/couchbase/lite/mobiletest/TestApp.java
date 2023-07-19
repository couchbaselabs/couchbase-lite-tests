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
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.ReplicatorService;
import com.couchbase.lite.mobiletest.util.StringUtils;


public abstract class TestApp {
    public static final String HEADER_PROTOCOL_VERSION = "CBLTest-API-Version".toLowerCase(Locale.getDefault());
    public static final int DEFAULT_PROTOCOL_VERSION = 1;
    public static final List<Integer> KNOWN_VERSIONS
        = Collections.unmodifiableList(Arrays.asList(DEFAULT_PROTOCOL_VERSION));

    public static final String HEADER_CLIENT = "CBLTest-Client-ID".toLowerCase(Locale.getDefault());
    public static final String DEFAULT_CLIENT = "c0ffee00-c0c0-50da-c01a-de1ec7ab1e00";
    public static final String HEADER_SERVER = "CBLTest-Server-ID";

    private static final AtomicReference<TestApp> APP = new AtomicReference<>();
    private static final AtomicReference<String> APP_ID = new AtomicReference<>();

    public static void init(@NonNull TestApp app) {
        if (!APP.compareAndSet(null, app)) {
            throw new IllegalStateException("Attempt to re-initialize the Test App");
        }
        app.init();
    }

    @NonNull
    public static TestApp getApp() {
        final TestApp app = APP.get();
        if (app == null) { throw new IllegalStateException("Test App has not been initialized"); }
        return app;
    }


    private final Map<String, Memory> symTabs = new HashMap<>();

    private final AtomicReference<DatabaseService> dbSvc = new AtomicReference<>();
    private final AtomicReference<ReplicatorService> replSvc = new AtomicReference<>();

    private Dispatcher dispatcher;

    protected abstract void initCBL();

    @NonNull
    public abstract String getPlatform();

    @NonNull
    public abstract Map<String, Object> getSystemInfo();

    @NonNull
    public abstract String encodeBase64(@NonNull byte[] hashBytes);

    @NonNull
    public abstract byte[] decodeBase64(@NonNull String encodedBytes);

    @Nullable
    public abstract InputStream getAsset(@NonNull String name);

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

    // The dispatcher is down here because it probably takes it a while to initialize.
    // Do it early, before showing the UI...
    @NonNull
    public final Dispatcher getDispatcher() { return dispatcher; }

    @NonNull
    public final List<Certificate> getAuthenticatorCertsList() throws CertificateException, IOException {
        final CertificateFactory certFactory = CertificateFactory.getInstance("X.509");

        final List<Certificate> certsList = new ArrayList<>();
        try (InputStream cert = getAsset("client-ca.der")) {
            certsList.add(certFactory.generateCertificate(cert));
        }

        return certsList;
    }

    @NonNull
    public final Memory getMemory(@NonNull String client) {
        Memory mem = symTabs.get(client);
        if (mem != null) { return mem; }

        mem = new Memory(client);
        symTabs.put(client, mem);

        return mem;
    }

    @NonNull
    public final DatabaseService getDbSvc() {
        final DatabaseService mgr = dbSvc.get();
        if (mgr == null) { dbSvc.compareAndSet(null, new DatabaseService()); }
        return dbSvc.get();
    }

    @NonNull
    public final ReplicatorService getReplSvc() {
        final ReplicatorService mgr = replSvc.get();
        if (mgr == null) { replSvc.compareAndSet(null, new ReplicatorService()); }
        return replSvc.get();
    }

    public final void reset(@NonNull TypedMap req, @NonNull Memory mem) {
        final ReplicatorService rMgr = replSvc.getAndSet(null);
        if (rMgr != null) { rMgr.reset(mem); }

        final DatabaseService dMgr = dbSvc.getAndSet(null);
        if (dMgr != null) { dMgr.reset(req, mem); }

        final String client = mem.getClient();
        symTabs.remove(client);

        final Memory newMem = getMemory(client);

        getDbSvc().init(req, newMem);

        getReplSvc().init(req, newMem);
    }

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

        // The dispatcher is down here because it probably takes it a while to initialize.
        // Do it early, before showing the UI...
        dispatcher = new Dispatcher(this);
        dispatcher.init();
    }
}
