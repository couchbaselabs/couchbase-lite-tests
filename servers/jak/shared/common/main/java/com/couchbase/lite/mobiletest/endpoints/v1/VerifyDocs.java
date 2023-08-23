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

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.changes.Snapshot;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;


@SuppressWarnings({"PMD.UnusedPrivateField", "PMD.SingularField"})
public class VerifyDocs extends UpdateItemEndpoint {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_SNAPSHOT = "snapshot";
    private static final String KEY_CHANGES = "changes";

    private static final String KEY_RESULT = "result";
    private static final String KEY_DESCRIPTION = "description";
    private static final String KEY_EXPECTED = "expected";
    private static final String KEY_ACTUAL = "actual";
    private static final String KEY_DOCUMENT = "document";

    private static final String KEY_DIFFS = "differences";
    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_DOC_ID = "id";
    private static final String KEY_PATH = "keyPath";
    private static final String KEY_CHANGE_TYPE = "changeType";


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

        final List<Snapshot.Difference> diffs
            = ctxt.getSnapshot(snapshotId).compare(ctxt, dbSvc.getOpenDb(ctxt, dbName), getDelta(changes));

        if (diffs.isEmpty()) {
            final Map<String, Object> resp = new HashMap<>();
            resp.put(KEY_DESCRIPTION, "Success");
            resp.put(KEY_RESULT, true);
            return resp;
        }

        return dumbDownResponse(diffs.get(0));
        //return makeResponse(diffs);
    }

    @NonNull
    private Map<String, Object> dumbDownResponse(@NonNull Snapshot.Difference diff) {
        final StringBuilder desc = new StringBuilder("Document '");
        desc.append(diff.docId).append("' in '").append(diff.collFqn);
        if (diff.keyPath != null) { desc.append(" at key path ").append(diff.keyPath); }
        desc.append(": ").append(diff.description);

        final Map<String, Object> resp = new HashMap<>();
        if (diff.content != null) { resp.put(KEY_DOCUMENT, diff.content); }
        resp.put(KEY_DESCRIPTION, desc.toString());
        resp.put(KEY_EXPECTED, diff.expected);
        resp.put(KEY_ACTUAL, diff.actual);

        resp.put(KEY_RESULT, false);

        return resp;
    }

    @SuppressWarnings("PMD.UnusedPrivateMethod")
    @NonNull
    private Map<String, Object> makeResponse(@NonNull List<Snapshot.Difference> differences) {
        final List<Map<String, Object>> diffs = new ArrayList<>();
        for (Snapshot.Difference difference: differences) {
            final Map<String, Object> diff = new HashMap<>();
            diff.put(KEY_DATABASE, difference.dbName);
            diff.put(KEY_COLLECTION, difference.collFqn);
            diff.put(KEY_DOC_ID, difference.docId);
            diff.put(KEY_PATH, difference.keyPath);
            diff.put(KEY_CHANGE_TYPE, difference.type);
            diff.put(KEY_EXPECTED, difference.expected);
            diff.put(KEY_ACTUAL, difference.actual);
            diff.put(KEY_DESCRIPTION, difference.description);
            diff.put(KEY_DOCUMENT, difference.content);
            diffs.add(diff);
        }

        final Map<String, Object> resp = new HashMap<>();
        resp.put(KEY_DIFFS, diffs);
        resp.put(KEY_RESULT, false);

        return resp;
    }
}

