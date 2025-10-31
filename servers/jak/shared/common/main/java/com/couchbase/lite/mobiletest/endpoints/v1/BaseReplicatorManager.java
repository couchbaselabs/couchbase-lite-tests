//
// Copyright (c) 2025 Couchbase, Inc All rights reserved.
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
import java.util.EnumMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.DocumentFlag;
import com.couchbase.lite.DocumentReplication;
import com.couchbase.lite.ReplicatedDocument;
import com.couchbase.lite.ReplicatorProgress;
import com.couchbase.lite.ReplicatorStatus;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.json.ErrorBuilder;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedList;


public class BaseReplicatorManager {
    protected static final String KEY_REPL_ID = "id";

    protected static final String KEY_NAMES = "names";
    protected static final String KEY_CHANNELS = "channels";
    protected static final String KEY_DOCUMENT_IDS = "documentIDs";
    protected static final String KEY_PUSH_FILTER = "pushFilter";
    protected static final String KEY_PULL_FILTER = "pullFilter";
    protected static final String KEY_CONFLICT_RESOLVER = "conflictResolver";
    protected static final String KEY_NAME = "name";
    protected static final String KEY_PARAMS = "params";
    protected static final String FILTER_DELETED = "deletedDocumentsOnly";
    protected static final String FILTER_DOC_ID = "documentIDs";
    protected static final String KEY_DOC_IDS = "documentIDs";
    protected static final String KEY_AUTHENTICATOR = "authenticator";
    protected static final String KEY_AUTH_TYPE = "type";
    protected static final String AUTH_TYPE_BASIC = "basic";
    protected static final String KEY_BASIC_AUTH_USER = "username";
    protected static final String KEY_BASIC_AUTH_PASSWORD = "password";
    protected static final String AUTH_TYPE_SESSION = "session";

    // Replicator status
    protected static final String KEY_REPL_ACTIVITY = "activity";
    protected static final String KEY_REPL_PROGRESS = "progress";
    protected static final String KEY_REPL_DOCS = "documents";
    protected static final String KEY_REPL_DOCS_COMPLETE = "completed";
    protected static final String KEY_REPL_COLLECTION = "collection";
    protected static final String KEY_REPL_DOC_ID = "documentID";
    protected static final String KEY_REPL_PUSH = "isPush";
    protected static final String KEY_REPL_FLAGS = "flags";

    protected static final String KEY_REPL_ERROR = "error";

    protected static final Set<String> LEGAL_COLLECTION_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_NAMES);
        l.add(KEY_CHANNELS);
        l.add(KEY_DOCUMENT_IDS);
        l.add(KEY_PUSH_FILTER);
        l.add(KEY_PULL_FILTER);
        l.add(KEY_CONFLICT_RESOLVER);
        LEGAL_COLLECTION_KEYS = Collections.unmodifiableSet(l);
    }

    protected static final Set<String> LEGAL_REPL_ID_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_REPL_ID);
        LEGAL_REPL_ID_KEYS = Collections.unmodifiableSet(l);
    }

    private static final EnumMap<DocumentFlag, String> DOC_FLAGS;
    static {
        final EnumMap<DocumentFlag, String> m = new EnumMap<>(DocumentFlag.class);
        m.put(DocumentFlag.DELETED, "DELETED");
        m.put(DocumentFlag.ACCESS_REMOVED, "ACCESSREMOVED");
        DOC_FLAGS = m;
    }

    @NonNull
    protected final DatabaseService dbSvc;

    public BaseReplicatorManager(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    protected final Map<String, Object> parseReplStatus(
        @NonNull ReplicatorStatus replStatus,
        @Nullable List<DocumentReplication> docs) {
        final Map<String, Object> resp = new HashMap<>();

        resp.put(KEY_REPL_ACTIVITY, replStatus.getActivityLevel().toString());

        final CouchbaseLiteException err = replStatus.getError();
        if (err != null) { resp.put(KEY_REPL_ERROR, new ErrorBuilder(new CblApiFailure(err)).build()); }

        final Map<String, Object> progress = new HashMap<>();
        final ReplicatorProgress replProgress = replStatus.getProgress();
        progress.put(KEY_REPL_DOCS_COMPLETE, replProgress.getCompleted() >= replProgress.getTotal());
        resp.put(KEY_REPL_PROGRESS, progress);

        if (docs != null) {
            final List<Map<String, Object>> docRepls = getReplicatedDocs(docs);
            if (!docRepls.isEmpty()) { resp.put(KEY_REPL_DOCS, docRepls); }
        }
        return resp;
    }

    @NonNull
    private List<Map<String, Object>> getReplicatedDocs(@NonNull List<DocumentReplication> replicatedDocs) {
        final List<Map<String, Object>> docRepls = new ArrayList<>();
        for (DocumentReplication replicatedDoc: replicatedDocs) {
            for (ReplicatedDocument replDoc: replicatedDoc.getDocuments()) {
                final Map<String, Object> docRepl = new HashMap<>();

                docRepl.put(KEY_REPL_COLLECTION, replDoc.getCollectionScope() + "." + replDoc.getCollectionName());

                docRepl.put(KEY_REPL_DOC_ID, replDoc.getID());

                docRepl.put(KEY_REPL_PUSH, replicatedDoc.isPush());

                final List<String> flagList = new ArrayList<>();
                for (DocumentFlag flag: replDoc.getFlags()) { flagList.add(DOC_FLAGS.get(flag)); }
                docRepl.put(KEY_REPL_FLAGS, flagList);

                final CouchbaseLiteException err = replDoc.getError();
                if (err != null) { docRepl.put(KEY_REPL_ERROR, new ErrorBuilder(new CblApiFailure(err)).build()); }

                docRepls.add(docRepl);
            }
        }
        return docRepls;
    }

    @Nullable
    protected final List<String> getList(@Nullable TypedList spec) {
        if (spec == null) { return null; }
        final int n = spec.size();
        final List<String> list = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            final String item = spec.getString(i);
            if (item != null) { list.add(item); }
        }
        return list;
    }
}
