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
package com.couchbase.lite.mobiletest.tools;

import androidx.annotation.NonNull;

import java.util.ArrayList;
import java.util.EnumSet;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.DocumentFlag;
import com.couchbase.lite.DocumentReplication;
import com.couchbase.lite.ReplicatedDocument;
import com.couchbase.lite.ReplicatorProgress;
import com.couchbase.lite.ReplicatorStatus;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;


public class ReplicatorStatusBuilder {
    private static final String KEY_REPL_ACTIVITY = "activity";
    private static final String KEY_REPL_PROGRESS = "progress";
    private static final String KEY_REPL_DOCS = "documents";
    private static final String KEY_REPL_DOCS_COMPLETE = "completed";
    private static final String KEY_REPL_COLLECTION = "collection";
    private static final String KEY_REPL_DOC_ID = "documentID";
    private static final String KEY_REPL_PUSH = "isPush";
    private static final String KEY_REPL_FLAGS = "flags";
    private static final String KEY_REPL_ERROR = "error";


    @NonNull
    private final List<DocumentReplication> replicatedDocs;
    @NonNull
    private final ReplicatorStatus replStatus;

    public ReplicatorStatusBuilder(
        @NonNull ReplicatorStatus replStatus,
        @NonNull List<DocumentReplication> replicatedDocs) {
        this.replStatus = replStatus;
        this.replicatedDocs = replicatedDocs;
    }

    @NonNull
    public Map<String, Object> build() {
        final List<Map<String, Object>> docRepls = new ArrayList<>();
        for (DocumentReplication replicatedDoc: replicatedDocs) {
            for (ReplicatedDocument replDoc: replicatedDoc.getDocuments()) {
                final Map<String, Object> docRepl = new HashMap<>();

                docRepl.put(KEY_REPL_COLLECTION, replDoc.getCollectionScope() + "." + replDoc.getCollectionName());

                docRepl.put(KEY_REPL_DOC_ID, replDoc.getID());

                if (replicatedDoc.isPush()) { docRepl.put(KEY_REPL_PUSH, Boolean.TRUE); }

                final EnumSet<DocumentFlag> flags = replDoc.getFlags();
                if (!flags.isEmpty()) {
                    final List<String> flagList = new ArrayList<>();
                    for (DocumentFlag flag: flags) { flagList.add(flag.toString()); }
                    docRepl.put(KEY_REPL_FLAGS, flagList);
                }

                final CouchbaseLiteException err = replDoc.getError();
                if (err != null) { docRepl.put(KEY_REPL_ERROR, new ErrorBuilder(new CblApiFailure(err)).build()); }

                docRepls.add(docRepl);
            }
        }

        final Map<String, Object> progress = new HashMap<>();
        final ReplicatorProgress replProgress = replStatus.getProgress();
        progress.put(KEY_REPL_DOCS_COMPLETE, replProgress.getCompleted() >= replProgress.getTotal());

        final Map<String, Object> resp = new HashMap<>();

        if (!docRepls.isEmpty()) { resp.put(KEY_REPL_DOCS, docRepls); }

        final CouchbaseLiteException err = replStatus.getError();
        if (err != null) { resp.put(KEY_REPL_ERROR, new ErrorBuilder(new CblApiFailure(err)).build()); }

        resp.put(KEY_REPL_PROGRESS, progress);

        resp.put(KEY_REPL_ACTIVITY, replStatus.getActivityLevel().toString());

        return resp;
    }
}
