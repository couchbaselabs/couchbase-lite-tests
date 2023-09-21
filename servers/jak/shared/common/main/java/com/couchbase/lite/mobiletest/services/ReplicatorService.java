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
package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import java.util.UUID;

import com.couchbase.lite.Collection;
import com.couchbase.lite.Document;
import com.couchbase.lite.DocumentFlag;
import com.couchbase.lite.DocumentReplication;
import com.couchbase.lite.ReplicationFilter;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.Scope;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public class ReplicatorService {
    static class DeletedDocFilter implements ReplicationFilter {
        @Override
        public boolean filtered(@NonNull Document ignore, @NonNull EnumSet<DocumentFlag> flags) {
            return flags.contains(DocumentFlag.DELETED);
        }
    }

    static class DocIdFilter implements ReplicationFilter {
        public static final String DOT = ".";

        @NonNull
        private final Set<String> permittedDocs;

        DocIdFilter(@NonNull Set<String> docs) { permittedDocs = docs; }

        @Override
        public boolean filtered(@NonNull Document document, @NonNull EnumSet<DocumentFlag> ignore) {
            final Collection collection = document.getCollection();
            return permittedDocs.contains(
                ((collection == null) ? Scope.DEFAULT_NAME : collection.getScope().getName())
                    + DOT
                    + ((collection == null) ? Collection.DEFAULT_NAME : collection.getName())
                    + DOT
                    + document.getId());
        }
    }


    public void init(@NonNull TestContext ignore1, @NonNull TypedMap ignore2) {
        // nothing to do here...
    }

    @NonNull
    public String addRepl(@NonNull TestContext ctxt, @NonNull Replicator repl) {
        final String replId = UUID.randomUUID().toString();
        ctxt.addRepl(replId, repl);
        return replId;
    }

    public void addDocListener(@NonNull TestContext ctxt, @NonNull String replId, @NonNull Replicator repl) {
        final DocReplListener listener = new DocReplListener();
        repl.addDocumentReplicationListener(listener);
        ctxt.addDocReplListener(replId, listener);
    }

    @Nullable
    public Replicator getRepl(@NonNull TestContext ctxt, @NonNull String replId) { return ctxt.getRepl(replId); }

    @Nullable
    public List<DocumentReplication> getReplicatedDocs(@NonNull TestContext ctxt, @NonNull String replId) {
        final DocReplListener listener = ctxt.getDocReplListener(replId);
        return (listener == null) ? null : listener.getReplicatedDocs();
    }

    @NonNull
    public ReplicationFilter getDeletedDocFilter() { return new DeletedDocFilter(); }

    @NonNull
    public ReplicationFilter getDocIdFilter(@NonNull Set<String> permitted) { return new DocIdFilter(permitted); }
}
