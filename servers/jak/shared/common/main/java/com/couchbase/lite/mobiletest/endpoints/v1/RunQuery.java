//
// Copyright (c) 2024 Couchbase, Inc All rights reserved.
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
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.Database;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public class RunQuery {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_QUERY = "query";
    private static final String KEY_RESULTS = "results";

    private static final Set<String> LEGAL_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_QUERY);
        LEGAL_KEYS = Collections.unmodifiableSet(l);
    }


    @NonNull
    private final DatabaseService dbSvc;

    public RunQuery(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @SuppressWarnings("PMD.PrematureDeclaration")
    @NonNull
    public Map<String, Object> runQuery(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_KEYS);

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Query request doesn't specify a database"); }
        final Database db = dbSvc.getOpenDb(ctxt, dbName);

        String query = req.getString(KEY_QUERY);
        if (query == null) { throw new ClientError("Query request doesn't specify a query"); }
        query = query.trim();
        if (query.isEmpty()) { throw new ClientError("Query request specifies an empty query"); }

        final Map<String, Object> ret = new HashMap<>();
        ret.put(KEY_RESULTS, dbSvc.runQuery(db, query));

        return ret;
    }
}
