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

import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;


@SuppressWarnings({"PMD.UnusedPrivateField", "PMD.SingularField"})
public class VerifyDocs extends UpdateItemEndpoint {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_SNAPSHOT = "snapshot";
    private static final String KEY_CHANGES = "changes";

    private static final Set<String> LEGAL_VALIDATE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_SNAPSHOT);
        l.add(KEY_CHANGES);
        LEGAL_VALIDATE_KEYS = Collections.unmodifiableSet(l);
    }
    public VerifyDocs(@NonNull DatabaseService dbSvc) { super(dbSvc); }

    @NonNull
    public Map<String, Object> verify(@NonNull TypedMap req, @NonNull TestContext ctxt) {
        req.validate(LEGAL_VALIDATE_KEYS);

        final String snapshotId = req.getString(KEY_SNAPSHOT);
        if (snapshotId == null) { throw new ClientError("Verify documents request doesn't specify a snapshot"); }

        final TypedList changes = req.getList(KEY_CHANGES);
        if (changes == null) { throw new ClientError("Verify documents request is empty"); }

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Verify documents request doesn't specify a database"); }

        return ctxt.getSnapshot(snapshotId).compare(ctxt, dbSvc.getOpenDb(ctxt, dbName), getDelta(changes));
    }
}

