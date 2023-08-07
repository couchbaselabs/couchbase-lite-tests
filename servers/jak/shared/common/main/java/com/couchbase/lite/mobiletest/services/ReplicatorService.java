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
import java.util.Map;
import java.util.UUID;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.Replicator;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;


public class ReplicatorService {
    private static final String SYM_OPEN_REPLS = "~OPEN_REPLS";

    public void reset(@NonNull Memory memory) {
        final Map<?, ?> repls = memory.remove(SYM_OPEN_REPLS, Map.class);
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
        TypedMap liveRepls = mem.getMap(SYM_OPEN_REPLS);
        if (liveRepls == null) {
            mem.put(SYM_OPEN_REPLS, new HashMap<>());
            // liveRepls cannot be null
            liveRepls = mem.getMap(SYM_OPEN_REPLS);
        }
        liveRepls.put(replId, repl);
        return replId;
    }

    @Nullable
    public Replicator getRepl(@NonNull Memory mem, @NonNull String replId) {
        final TypedMap liveRepls = mem.getMap(SYM_OPEN_REPLS);
        return (liveRepls == null) ? null : liveRepls.get(replId, Replicator.class);
    }
}
