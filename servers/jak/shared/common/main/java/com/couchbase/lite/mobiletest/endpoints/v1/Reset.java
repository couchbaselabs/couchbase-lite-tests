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

import java.util.Collections;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class Reset {
    public static final String KEY_CLIENT = "client";
    private static final String KEY_TEST_NAME = "name";
    private static final String KEY_DATASETS = "datasets";

    private static final Set<String> LEGAL_START_TEST_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_CLIENT);
        l.add(KEY_TEST_NAME);
        l.add(KEY_DATASETS);
        LEGAL_START_TEST_KEYS = Collections.unmodifiableSet(l);
    }


    @NonNull
    private final TestApp app;

    public Reset(@NonNull TestApp app) { this.app = app; }

    @NonNull
    public Map<String, Object> startTest(@Nullable TestContext context, @NonNull TypedMap req) {
        if (context != null) { throw new ClientError("Previous test was not ended: " + context.getName()); }
        req.validate(LEGAL_START_TEST_KEYS);

        final String client = req.getString(KEY_CLIENT);
        if (client == null) { throw new ServerError("No client supplied for startTest"); }

        final String testName = req.getString(KEY_TEST_NAME);
        if (testName == null) { throw new ClientError("No name supplied for startTest"); }

        final TypedMap datasets = req.getMap(KEY_DATASETS);
        if (datasets == null) { throw new ClientError("No datasets specified in init"); }

        setup(client, testName, datasets);

        return Collections.emptyMap();
    }

    @NonNull
    public Map<String, Object> endTest(@Nullable TestContext context, @NonNull TypedMap req) {
        final TestContext ctxt = TestContext.validateContext(context);
        req.validate(Collections.emptySet());

        cleanup(ctxt, ctxt.getName());

        return Collections.emptyMap();
    }

    @NonNull
    public final Map<String, Object> reset(@Nullable TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_START_TEST_KEYS);

        final String client;
        if (ctxt == null) {
            client = req.getString(KEY_CLIENT);
            if (client == null) { throw new ServerError("Client is null"); }
        }
        else {
            client = ctxt.getClient();
            cleanup(ctxt, ctxt.getName());
        }

        String testName = req.getString(KEY_TEST_NAME);
        if (testName == null) { testName = "UNNAMED"; }
        setup(client, testName, req.getMap(KEY_DATASETS));

        return Collections.emptyMap();
    }

    private void setup(@NonNull String client, @NonNull String testName, @Nullable TypedMap datasets) {
        Log.i("RESET", ">>>>> BEGIN TEST: " + testName);

        final TestContext ctxt = app.createTestContext(client, testName);

        final DatabaseService dbSvc = app.getDbSvc();
        dbSvc.init(ctxt);
        app.getReplSvc().init(ctxt);

        if (datasets != null) { installDatasets(ctxt, dbSvc, datasets); }
    }

    private void cleanup(@NonNull TestContext ctxt, @NonNull String testName) {
        app.clearReplSvc();
        app.clearDbSvc();
        ctxt.close();

        app.deleteTestContext(ctxt.getClient());

        Log.i("RESET", "<<<<< END TEST: " + testName);
    }

    private void installDatasets(
        @NonNull TestContext ctxt,
        @NonNull DatabaseService dbSvc,
        @NonNull TypedMap datasets) {
        final Set<String> datasetNames = datasets.getKeys();
        if (datasetNames.isEmpty()) { return; }

        for (String dataset: datasetNames) {
            final TypedList databases = datasets.getList(dataset);
            if ((databases == null) || (databases.size() <= 0)) {
                throw new ClientError("No target databases for in dataset " + dataset + " in init");
            }
            for (int i = 0; i < databases.size(); i++) {
                final String dbName = databases.getString(i);
                if (StringUtils.isEmpty(dbName)) {
                    throw new ClientError("Empty target database name in dataset " + dataset + " in init");
                }
                dbSvc.installDataset(ctxt, dataset, dbName);
            }
        }
    }
}

