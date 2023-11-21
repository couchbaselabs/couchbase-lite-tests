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

import com.couchbase.lite.Collection;
import com.couchbase.lite.Database;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.changes.Change;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public class UpdateDb extends UpdateItemEndpoint {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_UPDATES = "updates";

    private static final Set<String> LEGAL_UPDATES_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_UPDATES);
        LEGAL_UPDATES_KEYS = Collections.unmodifiableSet(l);
    }
    public UpdateDb(@NonNull DatabaseService dbSvc) { super(dbSvc); }

    @SuppressWarnings("PMD.PrematureDeclaration")
    @NonNull
    public Map<String, Object> updateDb(@NonNull TestContext context, @NonNull TypedMap req) {
        final TestContext ctxt = TestContext.validateContext(context);
        req.validate(LEGAL_UPDATES_KEYS);

        final TypedList updates = req.getList(KEY_UPDATES);
        if (updates == null) { throw new ClientError("Database update request is empty"); }

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Database update request doesn't specify a database"); }

        final Database db = dbSvc.getOpenDb(ctxt, dbName);
        for (Map.Entry<String, Map<String, Change>> collChanges: getDelta(updates).entrySet()) {
            final Collection collection = dbSvc.getCollection(ctxt, db, collChanges.getKey());
            for (Map.Entry<String, Change> change: collChanges.getValue().entrySet()) {
                change.getValue().updateDocument(dbSvc, collection);
            }
        }

        return Collections.emptyMap();
    }
}
