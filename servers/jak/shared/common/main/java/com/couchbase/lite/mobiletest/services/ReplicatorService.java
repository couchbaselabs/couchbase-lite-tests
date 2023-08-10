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

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.DocumentReplication;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.tools.DocReplListener;


public class ReplicatorService {
    private static final String SYM_REPLICATORS = "~REPLICATORS";
    private static final String SYM_LISTENERS = "~LISTENERS";

    public void reset(@NonNull Memory memory) {
        final Map<?, ?> repls = memory.remove(SYM_REPLICATORS, Map.class);
        if ((repls == null) || repls.isEmpty()) { return; }

        final TypedMap liveRepls = new TypedMap(repls);
        for (String key: liveRepls.getKeys()) {
            final Replicator repl = liveRepls.get(key, Replicator.class);
            if (repl != null) { repl.stop(); }
        }
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @SuppressWarnings("ConstantConditions")
    @NonNull
    public String addRepl(@NonNull Memory mem, @NonNull Replicator repl) {
        final String replId = UUID.randomUUID().toString();
        TypedMap liveRepls = mem.getMap(SYM_REPLICATORS);
        if (liveRepls == null) {
            mem.put(SYM_REPLICATORS, new HashMap<>());
            // liveRepls cannot be null
            liveRepls = mem.getMap(SYM_REPLICATORS);
        }
        liveRepls.put(replId, repl);
        return replId;
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @SuppressWarnings("ConstantConditions")
    public void addDocListener(@NonNull Memory mem, @NonNull String replId, @NonNull Replicator repl) {
        TypedMap liveListeners = mem.getMap(SYM_LISTENERS);
        if (liveListeners == null) {
            mem.put(SYM_LISTENERS, new HashMap<>());
            // liveRepls cannot be null
            liveListeners = mem.getMap(SYM_LISTENERS);
        }

        final DocReplListener listener = new DocReplListener();
        liveListeners.put(replId, listener);

        repl.addDocumentReplicationListener(listener);
    }

    @Nullable
    public Replicator getRepl(@NonNull Memory mem, @NonNull String replId) {
        final TypedMap liveRepls = mem.getMap(SYM_REPLICATORS);
        return (liveRepls == null) ? null : liveRepls.get(replId, Replicator.class);
    }

    @Nullable
    public List<DocumentReplication> getReplicatedDocs(@NonNull Memory mem, @NonNull String replId) {
        final TypedMap liveListeners = mem.getMap(SYM_LISTENERS);
        if (liveListeners != null) {
            final DocReplListener listener = liveListeners.get(replId, DocReplListener.class);
            if (listener != null) { return listener.getReplications(); }
        }
        return null;
    }
}
