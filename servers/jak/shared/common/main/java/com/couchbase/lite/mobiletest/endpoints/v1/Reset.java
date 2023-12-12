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

import java.util.Collections;
import java.util.HashSet;
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
    private static final String KEY_DATASETS = "datasets";

    private static final Set<String> LEGAL_RESET_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_TEST_NAME);
        l.add(KEY_DATASETS);
        LEGAL_RESET_KEYS = Collections.unmodifiableSet(l);
    }


    @NonNull
    private final TestApp app;

    public Reset(@NonNull TestApp app) { this.app = app; }

    @NonNull
    public final Map<String, Object> reset(@NonNull TestContext oldCtxt, @NonNull TypedMap req) {
        final String client = oldCtxt.getClient();

        final String endingTest = oldCtxt.getTestName();
        if (endingTest != null) { Log.p(TAG, "<<<<<<<<<< " + endingTest); }

        app.clearReplSvc();
        app.clearDbSvc();
        oldCtxt.close();

        final String startingTest = req.getString(KEY_TEST_NAME);
        Log.setLogger(startingTest);

        final TestContext ctxt = app.resetContext(client);
        final DatabaseService dbSvc = app.getDbSvc();
        dbSvc.init(ctxt);
        app.getReplSvc().init(ctxt);

        req.validate(LEGAL_RESET_KEYS);

        if (startingTest != null) {
            Log.p(TAG, ">>>>>>>>>> " + startingTest);
            ctxt.setTestName(startingTest);
        }

        final TypedMap datasets = req.getMap(KEY_DATASETS);
        if (datasets == null) { throw new ClientError("No datasets specified in init"); }
        installDatasets(ctxt, dbSvc, datasets);

        return Collections.emptyMap();
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

