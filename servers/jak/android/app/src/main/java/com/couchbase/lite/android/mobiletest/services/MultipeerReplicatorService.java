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
package com.couchbase.lite.android.mobiletest.services;

import androidx.annotation.NonNull;

import java.util.EnumSet;
import java.util.Set;
import java.util.UUID;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Document;
import com.couchbase.lite.DocumentFlag;
import com.couchbase.lite.MultipeerCollectionConfiguration;
import com.couchbase.lite.MultipeerReplicator;
import com.couchbase.lite.MultipeerReplicatorConfiguration;
import com.couchbase.lite.PeerInfo;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;


public class MultipeerReplicatorService {
    private static class DeletedDocFilter implements MultipeerCollectionConfiguration.ReplicationFilter {
        @Override
        public boolean filtered(
            @NonNull PeerInfo.PeerId peerId,
            @NonNull Document document,
            @NonNull EnumSet<DocumentFlag> flags) {
            return flags.contains(DocumentFlag.DELETED);
        }
    }

    private static class DocIdFilter implements MultipeerCollectionConfiguration.ReplicationFilter {
        @NonNull
        private final Set<String> permittedDocs;

        DocIdFilter(@NonNull Set<String> docs) { permittedDocs = docs; }

        @Override
        public boolean filtered(
            @NonNull PeerInfo.PeerId peerId,
            @NonNull Document document,
            @NonNull EnumSet<DocumentFlag> flags) {
            return permittedDocs.contains(DatabaseService.getDocumentFullName(document));
        }
    }


    @NonNull
    public String startReplicator(@NonNull TestContext ctxt, @NonNull MultipeerReplicatorConfiguration config) {
        final MultipeerReplicator repl;
        try { repl = new MultipeerReplicator(config); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed creating multipeer replicator", e); }

        final String replId = UUID.randomUUID().toString();
        ctxt.addMultipeerRepl(replId, repl);
        repl.start();

        return replId;
    }

    @NonNull
    public Set<PeerInfo.PeerId> getNeighbors(@NonNull TestContext ctxt, @NonNull String id) {
        final MultipeerReplicator repl = ctxt.getMultipeerRepl(id);
        if (repl == null) { throw new ClientError("No such replicator: " + id); }
        return repl.getNeighborPeers();
    }

    @NonNull
    public PeerInfo getPeerStatus(@NonNull TestContext ctxt, @NonNull String id, @NonNull PeerInfo.PeerId peer) {
        final MultipeerReplicator repl = ctxt.getMultipeerRepl(id);
        if (repl == null) { throw new ClientError("No such multipeer replicator: " + id); }
        return repl.getPeerInfo(peer);
    }

    // Unlike a standard replicator, a multipeer replicator cannot be restarted
    // When it is stopped we delete it from the context.
    public void stopReplicator(TestContext ctxt, @NonNull String id) {
        final MultipeerReplicator repl = ctxt.removeMultipeerRepl(id);
        if (repl == null) { throw new ClientError("No such multipeer replicator: " + id); }
        repl.stop();
    }

    @NonNull
    public MultipeerCollectionConfiguration.ReplicationFilter getDeletedDocFilter() {
        return new DeletedDocFilter();
    }

    @NonNull
    public MultipeerCollectionConfiguration.ReplicationFilter getDocIdFilter(@NonNull Set<String> permitted) {
        return new DocIdFilter(permitted);
    }
}
