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

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorStatus;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.factories.ReplicatorConfigBuilder;
import com.couchbase.lite.mobiletest.factories.ReplicatorStatusBuilder;
import com.couchbase.lite.mobiletest.util.Log;


public class ReplicatorService {
    private static final String TAG = "REPL_SVC";

    private static final String KEY_REPL_ID = "id";

    private static final String SYM_OPEN_REPLS = "~OPEN_REPLS";

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @NonNull
    public Map<String, Object> createReplV1(@NonNull TypedMap req, @NonNull Memory mem) {
        TypedMap liveRepls = mem.getMap(SYM_OPEN_REPLS);
        if (liveRepls == null) {
            mem.put(SYM_OPEN_REPLS, new HashMap<>());
            // liveRepls cannot be null
            liveRepls = mem.getMap(SYM_OPEN_REPLS);
        }

        final String replId = UUID.randomUUID().toString();
        final ReplicatorConfigBuilder configBuilder = new ReplicatorConfigBuilder(req, mem);
        final Replicator repl = new Replicator(configBuilder.build());
        liveRepls.put(replId, repl);

        repl.start(configBuilder.shouldReset());
        Log.i(TAG, "Started replicator: " + replId);

        final Map<String, Object> ret = new HashMap<>();
        ret.put(KEY_REPL_ID, replId);
        return ret;
    }

    @NonNull
    public Map<String, Object> getReplStatusV1(@NonNull TypedMap req, @NonNull Memory mem) {
        final String id = req.getString(KEY_REPL_ID);
        if (id == null) { throw new ClientError("Replicator id not specified"); }

        final TypedMap liveRepls = mem.getMap(SYM_OPEN_REPLS);
        if (liveRepls == null) { throw new ClientError("No such replicator: " + id); }

        final Replicator repl = liveRepls.get(id, Replicator.class);
        if (repl == null) { throw new ClientError("No such replicator: " + id); }

        final ReplicatorStatus replStatus = repl.getStatus();
        Log.i(TAG, "Replicator status: " + replStatus);

        return new ReplicatorStatusBuilder(replStatus).build();
    }

    public void reset(@NonNull Memory memory) {
        final Map<?, ?> repls = memory.remove(SYM_OPEN_REPLS, Map.class);
        if ((repls == null) || repls.isEmpty()) { return; }

        final TypedMap liveRepls = new TypedMap(repls);
        for (String key: liveRepls.getKeys()) {
            final Replicator repl = liveRepls.get(key, Replicator.class);
            if (repl != null) { repl.stop(); }
        }
    }

    public void init(TypedMap req, Memory mem) { }
}
