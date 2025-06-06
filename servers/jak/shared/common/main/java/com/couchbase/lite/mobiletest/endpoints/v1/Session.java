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

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class Session {
    private static final String TAG = "RESET";

    private static final String KEY_TEST_NAME = "test";
    private static final String KEY_DATABASES = "databases";
    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_DATASET = "dataset";
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

    private static final Set<String> LEGAL_DATABASE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_COLLECTIONS);
        l.add(KEY_DATASET);
        LEGAL_DATABASE_KEYS = Collections.unmodifiableSet(l);
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

    public Session(@NonNull TestApp app) { this.app = app; }

    @NonNull
    public Map<String, Object> newSession(@NonNull String newClient, @NonNull TypedMap req) {
        req.validate(LEGAL_SESSION_KEYS);

        final String sessionId = req.getString(KEY_ID);
        if (sessionId == null) { throw new ClientError("No new session ID specified"); }

        if (!sessionId.equals(newClient)) {
            throw new ClientError(
                "Current client (" + newClient + ") does not match new session ID (" + sessionId + ")");
        }

        final TestContext oldCtxt = app.getSessionUnchecked();
        final String oldClient = (oldCtxt == null) ? null : oldCtxt.getClient();
        if (oldClient != null) { Log.p(TAG, "<<<<<<<<<< END SESSION: " + oldClient); }

        endSession(app);

        final TestContext newCtxt = app.newSession(sessionId, req.getString(KEY_DATASET_VERSION));
        startSession(app, newCtxt);

        final TypedMap logConfig = req.getMap(KEY_LOGGING);
        if (logConfig == null) { Log.installDefaultLogger(); }
        else { setupRemoteLogger(sessionId, logConfig); }

        Log.p(TAG, ">>>>>>>>>> NEW SESSION: " + sessionId);

        return Collections.emptyMap();
    }

    @NonNull
    public final Map<String, Object> reset(@NonNull String client, @NonNull TypedMap req) {
        req.validate(LEGAL_RESET_KEYS);

        final TestContext oldCtxt = app.getSession(client);
        String testName = oldCtxt.getTestName();

        if (testName != null) { Log.p(TAG, "<<<<< END TEST: " + testName); }

        // preserve the dataset version across resets
        final String datasetVersion = oldCtxt.getDatasetVersion();

        endSession(app);

        final TestContext newCtxt = app.newSession(client, datasetVersion);
        final DatabaseService dbSvc = startSession(app, newCtxt);
        testName = req.getString(KEY_TEST_NAME);
        newCtxt.setTestName(testName);

        if (testName != null) { Log.p(TAG, ">>>>> START TEST: " + testName); }

        createDbs(newCtxt, dbSvc, req.getMap(KEY_DATABASES));

        return Collections.emptyMap();
    }

    private void setupRemoteLogger(@NonNull String sessionId, @NonNull TypedMap req) {
        req.validate(LEGAL_SETUP_LOGGING_KEYS);

        final String url = req.getString(KEY_URL);
        if (url == null) { throw new ClientError("No log slurper URL in logging config"); }

        final String tag = req.getString(KEY_TAG);
        if (tag == null) { throw new ClientError("No log tag in logging config"); }

        Log.installRemoteLogger(url, sessionId, tag);
    }

    private void createDbs(@NonNull TestContext ctxt, @NonNull DatabaseService dbSvc, @Nullable TypedMap databases) {
        if ((databases == null) || databases.isEmpty()) { return; }

        final Set<String> dbNames = databases.getKeys();
        for (String dbName: dbNames) {
            final TypedMap dbDesc = databases.getMap(dbName);

            if ((dbDesc == null) || dbDesc.isEmpty()) {
                createDb(ctxt, dbSvc, dbName, null);
                continue;
            }

            dbDesc.validate(LEGAL_DATABASE_KEYS);

            final String dataset = dbDesc.getString(KEY_DATASET);
            if (dataset != null) {
                if (dbDesc.containsKey(KEY_COLLECTIONS)) {
                    throw new ClientError(
                        "Both collections and dataset specified for database " + dbName + " in reset");
                }
                installDataset(ctxt, dbSvc, dbName, dataset);
                continue;
            }

            final TypedList collections = dbDesc.getList(KEY_COLLECTIONS);
            if ((collections == null) || collections.isEmpty()) {
                throw new ClientError("Null or empty collections list for database " + dbName + " in reset");
            }

            createDb(ctxt, dbSvc, dbName, collections);
        }
    }

    private static void createDb(
        @NonNull TestContext ctxt,
        @NonNull DatabaseService svc,
        @NonNull String dbName,
        @Nullable TypedList collections) {
        final List<String[]> collFqns = new ArrayList<>();
        if (collections != null) {
            for (int i = 0; i < collections.size(); i++) {
                final String fqn = collections.getString(i);
                if (fqn == null) { throw new ClientError("Null collection for database " + dbName + " in reset"); }
                collFqns.add(DatabaseService.parseCollectionFullName(fqn));
            }
        }
        svc.installDatabase(ctxt, dbName, collFqns);
    }

    private void installDataset(
        @NonNull TestContext ctxt,
        @NonNull DatabaseService dbSvc,
        @NonNull String dbName,
        @Nullable String dataset) {
        if (StringUtils.isEmpty(dataset)) {
            throw new ClientError("Dataset is null for database " + dbName + " in reset");
        }
        dbSvc.installDataset(ctxt, dataset, dbName);
    }

    @NonNull
    private DatabaseService startSession(@NonNull TestApp app, @NonNull TestContext ctxt) {
        final DatabaseService dbSvc = app.getDbSvc();
        dbSvc.init(ctxt);
        app.getReplSvc().init(ctxt);
        app.getListenerService().init(ctxt);
        return dbSvc;
    }

    private void endSession(@NonNull TestApp app) {
        app.clearReplSvc();
        app.clearListenerService();
        app.clearDbSvc();
    }
}

