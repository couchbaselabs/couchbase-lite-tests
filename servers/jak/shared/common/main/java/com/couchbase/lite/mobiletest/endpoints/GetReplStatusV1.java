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
package com.couchbase.lite.mobiletest.endpoints;

import androidx.annotation.NonNull;

import java.util.ArrayList;
import java.util.EnumMap;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.DocumentFlag;
import com.couchbase.lite.DocumentReplication;
import com.couchbase.lite.ReplicatedDocument;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorProgress;
import com.couchbase.lite.ReplicatorStatus;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.ReplicatorService;
import com.couchbase.lite.mobiletest.tools.ErrorBuilder;
import com.couchbase.lite.mobiletest.util.Log;


public class GetReplStatusV1 {
    private static final String TAG = "REPL_STATUS_V1";

    private static final String KEY_REPL_ID = "id";

    private static final String KEY_REPL_ACTIVITY = "activity";
    private static final String KEY_REPL_PROGRESS = "progress";
    private static final String KEY_REPL_DOCS = "documents";
    private static final String KEY_REPL_DOCS_COMPLETE = "completed";
    private static final String KEY_REPL_COLLECTION = "collection";
    private static final String KEY_REPL_DOC_ID = "documentID";
    private static final String KEY_REPL_PUSH = "isPush";
    private static final String KEY_REPL_FLAGS = "flags";
    private static final String KEY_REPL_ERROR = "error";

    private static final EnumMap<DocumentFlag, String> DOC_FLAGS;
    static {
        final EnumMap<DocumentFlag, String> m = new EnumMap<>(DocumentFlag.class);
        m.put(DocumentFlag.DELETED, "DELETED");
        m.put(DocumentFlag.ACCESS_REMOVED, "ACCESSREMOVED");
        DOC_FLAGS = m;
    }




    @NonNull
    private final ReplicatorService replSvc;

    public GetReplStatusV1(@NonNull ReplicatorService replSvc) { this.replSvc = replSvc; }

    @NonNull
    public Map<String, Object> getReplStatus(@NonNull TypedMap req, @NonNull Memory mem) {
        final String id = req.getString(KEY_REPL_ID);
        if (id == null) { throw new ClientError("Replicator id not specified"); }

        final Replicator repl = replSvc.getRepl(mem, id);
        if (repl == null) { throw new ClientError("No such replicator: " + id); }

        final ReplicatorStatus replStatus = repl.getStatus();
        Log.i(TAG, "Replicator status: " + replStatus);

        final Map<String, Object> resp = new HashMap<>();
        buildStatus(resp, replStatus);

        final List<DocumentReplication> docs = replSvc.getReplicatedDocs(mem, id);
        if (docs != null) {
            final List<Map<String, Object>> docRepls = getReplicatedDocs(docs);
            if (!docRepls.isEmpty()) { resp.put(KEY_REPL_DOCS, docRepls); }
        }

        return resp;
    }

    public void buildStatus(Map<String, Object> resp, @NonNull ReplicatorStatus replStatus) {
        final Map<String, Object> progress = new HashMap<>();
        final ReplicatorProgress replProgress = replStatus.getProgress();
        progress.put(KEY_REPL_DOCS_COMPLETE, replProgress.getCompleted() >= replProgress.getTotal());

        final CouchbaseLiteException err = replStatus.getError();
        if (err != null) { resp.put(KEY_REPL_ERROR, new ErrorBuilder(new CblApiFailure(err)).build()); }

        resp.put(KEY_REPL_PROGRESS, progress);

        resp.put(KEY_REPL_ACTIVITY, replStatus.getActivityLevel().toString());
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
}
