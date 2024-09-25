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
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class Reset {
    private static final String TAG = "RESET";

    private static final String KEY_TEST_NAME = "test";
    private static final String KEY_DATABASES = "databases";
    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_DATASET = "datasets";

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


    @NonNull
    private final TestApp app;

    public Reset(@NonNull TestApp app) { this.app = app; }

    @NonNull
    public final Map<String, Object> reset(@NonNull TestContext oldCtxt, @NonNull TypedMap req) {
        req.validate(LEGAL_RESET_KEYS);

        final String endingTest = oldCtxt.getTestName();
        if (endingTest != null) { Log.p(TAG, "<<<<<<<<<< " + endingTest); }

        final String client = oldCtxt.getClient();
        app.clearReplSvc();
        app.clearDbSvc();
        oldCtxt.close();

        final String startingTest = req.getString(KEY_TEST_NAME);
        Log.setLogger(startingTest);

        final TestContext ctxt = app.resetContext(client);
        final DatabaseService dbSvc = app.getDbSvc();
        dbSvc.init(ctxt);
        app.getReplSvc().init(ctxt);

        if (startingTest != null) {
            Log.p(TAG, ">>>>>>>>>> " + startingTest);
            ctxt.setTestName(startingTest);
        }

        createDbs(ctxt, dbSvc, req.getMap(KEY_DATABASES));

        return Collections.emptyMap();
    }

    private void createDbs(@NonNull TestContext ctxt, @NonNull DatabaseService dbSvc, @Nullable TypedMap databases) {
        if ((databases == null) || databases.isEmpty()) { return; }

        final Set<String> dbNames = databases.getKeys();
        for (String dbName: dbNames) {
            final TypedMap dbDesc = databases.getMap(dbName);

            if ((dbDesc == null) || dbDesc.isEmpty()) {
                createDb(ctxt, dbSvc, dbName, null);
                return;
            }

            dbDesc.validate(LEGAL_DATABASE_KEYS);

            final String dataset = dbDesc.getString(KEY_DATASET);
            if (dataset != null) {
                if (!dbDesc.containsKey(KEY_COLLECTIONS)) {
                    throw new ClientError(
                        "Both collections and dataset specified for database " + dbName + " in reset");
                }
                installDataset(ctxt, dbSvc, dbName, dataset);
                return;
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
}

