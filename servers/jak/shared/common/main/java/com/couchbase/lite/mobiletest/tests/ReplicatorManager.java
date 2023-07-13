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
package com.couchbase.lite.mobiletest.tests;

import androidx.annotation.NonNull;

import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import com.couchbase.lite.Replicator;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestException;
import com.couchbase.lite.mobiletest.util.Log;


public class ReplicatorManager {
    private static final String TAG = "REPLMGR";

    private static final String SYM_OPEN_REPLS = "~OPEN_REPLS";

    private static final String KEY_REPL_ID = "id";


    @NonNull
    public Map<String, Object> createRepl(@NonNull Map<String, Object> req, @NonNull Memory memory)
        throws TestException {
        Map<String, Object> liveRepls = memory.getMap(SYM_OPEN_REPLS);
        if (liveRepls == null) {
            liveRepls = new HashMap<>();
            memory.put(SYM_OPEN_REPLS, liveRepls);
        }

        final String replId = UUID.randomUUID().toString();
        final Replicator repl = new Replicator(new ReplicatorConfigBuilder(req, memory).build());
        liveRepls.put(replId, repl);

        repl.start();
        Log.i(TAG, "Started replicator: " + replId);

        final Map<String, Object> ret = new HashMap<>();
        ret.put(KEY_REPL_ID, replId);
        return ret;
    }

    public void reset(@NonNull Memory memory) {
        final Map<String, Object> liveRepls = memory.getMap(SYM_OPEN_REPLS);
        memory.put(SYM_OPEN_REPLS, null);

        if ((liveRepls == null) || liveRepls.isEmpty()) { return; }

        for (Object repl: liveRepls.values()) {
            if (!(repl instanceof Replicator)) {
                Log.e(TAG, "Attempt to close non-replicator: " + repl);
                continue;
            }

            ((Replicator) repl).stop();
        }
    }
}
