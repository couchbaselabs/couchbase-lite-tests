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
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.Database;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.changes.Snapshot;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;


@SuppressWarnings({"PMD.UnusedPrivateField", "PMD.SingularField"})
public class SnapshotDocs {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_DOCUMENTS = "documents";
    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_DOC_ID = "id";

    private static final Set<String> LEGAL_SNAPSHOT_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_DOCUMENTS);
        LEGAL_SNAPSHOT_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_DOC_ID_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_COLLECTION);
        l.add(KEY_DOC_ID);
        LEGAL_DOC_ID_KEYS = Collections.unmodifiableSet(l);
    }


    @NonNull
    private final DatabaseService dbSvc;

    public SnapshotDocs(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    public Map<String, Object> snapshot(@NonNull TypedMap req, @NonNull TestContext ctxt) {
        req.validate(LEGAL_SNAPSHOT_KEYS);

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Snapshot request doesn't specify a database"); }

        final TypedList docIds = req.getList(KEY_DOCUMENTS);
        if ((docIds == null) || docIds.isEmpty()) { throw new ClientError("Snapshot request specifies no docIds"); }

        final Database db = dbSvc.getOpenDb(ctxt, dbName);
        final Snapshot snapshot = new Snapshot(dbSvc);

        final int n = docIds.size();
        for (int i = 0; i < n; i++) {
            final TypedMap docId = docIds.getMap(i);
            if (docId == null) { throw new ClientError("Null docId @ " + i); }
            docId.validate(LEGAL_DOC_ID_KEYS);

            final String collFqn = docId.getString(KEY_COLLECTION);
            if (collFqn == null) { throw new ClientError("Null collection name @ " + i); }

            final String id = docId.getString(KEY_DOC_ID);
            if (id == null) { throw new ClientError("Null id @ " + i); }

            snapshot.snapshotDocument(ctxt, db, collFqn, id);
        }

        final Map<String, Object> resp = new HashMap<>();
        resp.put(KEY_DOC_ID, ctxt.addSnapshot(snapshot));

        return resp;
    }
}
