//
// Copyright (c) 2023 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.mobiletest.endpoints.v1;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.util.Collections;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.StringUtils;

@SuppressFBWarnings({"EI_EXPOSE_REP", "EI_EXPOSE_REP2"})
public class Session {
    private static final String DEFAULT_DATASET_VERSION = "4.0";

    private static final String TAG = "RESET";

    private static final String KEY_TEST_NAME = "test";
    private static final String KEY_DATABASES = "databases";
    private static final String KEY_ID = "id";
    private static final String KEY_DATASET_VERSION = "dataset_version";
    private static final String KEY_LOGGING = "logging";

    private static final String KEY_URL = "url";
    private static final String KEY_TAG = "tag";

    private static final Set<String> LEGAL_SESSION_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_ID);
        l.add(KEY_DATASET_VERSION);
        l.add(KEY_LOGGING);
        LEGAL_SESSION_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_RESET_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_TEST_NAME);
        l.add(KEY_DATABASES);
        LEGAL_RESET_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_SETUP_LOGGING_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_URL);
        l.add(KEY_TAG);
        LEGAL_SETUP_LOGGING_KEYS = Collections.unmodifiableSet(l);
    }


    @NonNull
    private final TestApp app;
    @NonNull
    private final String client;
    @NonNull
    private final File rootDir;
    @NonNull
    private final File tmpDir;

    @Nullable
    private String datasetVersion;
    @Nullable
    private TestContext context;

    public Session(@NonNull TestApp app, @NonNull String client) {
        this.app = app;
        this.client = client;

        final FileUtils fileUtils = new FileUtils();
        final File rootDir = new File(TestApp.getApp().getFilesDir(), "tests_" + StringUtils.randomString(6));
        if (rootDir.exists() && !fileUtils.deleteRecursive(rootDir)) {
            throw new ServerError("Failed deleting session root directory: " + rootDir);
        }

        if (!rootDir.mkdirs()) { throw new ServerError("Failed creating session root directory: " + rootDir); }
        this.rootDir = rootDir;

        final File tmpDir = new File(rootDir, "tmp");
        if (!tmpDir.mkdirs()) { throw new ServerError("Failed creating session tmp directory: " + tmpDir); }
        this.tmpDir = tmpDir;
    }

    @NonNull
    public Map<String, Object> newSession(@NonNull TypedMap req) {
        req.validate(LEGAL_SESSION_KEYS);

        final String sessionId = req.getString(KEY_ID);
        if (sessionId == null) { throw new ClientError("No new session ID specified"); }

        if (!sessionId.equals(client)) {
            throw new ClientError(
                "Current client (" + client + ") doesn't match ID for new session: " + sessionId);
        }

        final Session oldSession = app.getSession();
        if (oldSession != null) { oldSession.close(); }

        final String dsVersion = req.getString(KEY_DATASET_VERSION);
        this.datasetVersion = (dsVersion != null) ? dsVersion : DEFAULT_DATASET_VERSION;

        this.context = null;

        final TypedMap logConfig = req.getMap(KEY_LOGGING);
        if (logConfig == null) { Log.installDefaultLogger(); }
        else { setupRemoteLogger(sessionId, logConfig); }

        app.newSession(this);
        Log.p(TAG, ">>>>>>>>>> NEW SESSION: " + sessionId);

        return Collections.emptyMap();
    }

    @NonNull
    public final Map<String, Object> reset(@NonNull TypedMap req) {
        req.validate(LEGAL_RESET_KEYS);

        final Session curSession = app.getSession();
        if (curSession == null) {
            throw new ClientError("Attempt to reset a session that doesn't exist");
        }

        if (!client.equals(curSession.client)) {
            throw new ClientError("Attempt to reset a session for an unknown client: " + client);
        }

        final TestContext oldContext = curSession.context;
        if (oldContext != null) { oldContext.close(app); }

        final String testName = req.getString(KEY_TEST_NAME);
        final TestContext newCtxt = (testName == null) ? null : new TestContext(app, curSession, testName);
        curSession.context = newCtxt;

        if (newCtxt != null) { newCtxt.createDbs(app.getDbSvc(), req.getMap(KEY_DATABASES)); }

        return Collections.emptyMap();
    }


    @NonNull
    public File getRootDir() { return rootDir; }

    @NonNull
    public File getTmpDir() { return tmpDir; }

    @NonNull
    public String getDatasetVersion() {
        if (datasetVersion == null) { throw new ClientError("Dataset version required but not set"); }
        return datasetVersion;
    }

    @Nullable
    public TestContext getTestContext() { return context; }

    @NonNull
    public TestContext getVerifiedContext(@NonNull String client) {
        if (context == null) { throw new ClientError("Attempt to use a test context before it has been created"); }
        if (!this.client.equals(client)) {
            throw new ClientError("Attempt to use a test context for an unknown client");
        }
        return context;
    }

    public void close() {
        final TestContext oldContext = this.context;
        context = null;
        if (oldContext != null) { oldContext.close(app); }

        if (!new FileUtils().deleteRecursive(rootDir)) {
            Log.err(TAG, "Failed deleting tmp directory on reset: " + rootDir);
        }

        Log.p(TAG, "<<<<<<<<<< END SESSION: " + client);
    }

    private void setupRemoteLogger(@NonNull String sessionId, @NonNull TypedMap req) {
        req.validate(LEGAL_SETUP_LOGGING_KEYS);

        final String url = req.getString(KEY_URL);
        if (url == null) { throw new ClientError("No log slurper URL in logging config"); }

        final String tag = req.getString(KEY_TAG);
        if (tag == null) { throw new ClientError("No log tag in logging config"); }

        Log.installRemoteLogger(url, sessionId, tag);
    }
}

