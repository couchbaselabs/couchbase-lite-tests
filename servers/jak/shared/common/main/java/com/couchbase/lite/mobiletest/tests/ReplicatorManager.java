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

import java.util.List;

import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorConfiguration;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestException;
import com.couchbase.lite.mobiletest.util.Log;


public class ReplicatorManager {
    private static final String TAG = "REPLMGR";

    private static final String SYM_OPEN_REPLS = "~OPEN_REPLS";

    @NonNull
    public Replicator createRepl(@NonNull ReplicatorConfiguration config, @NonNull Memory memory) throws TestException {
        final Replicator repl = new Replicator(config);
        memory.addToList(SYM_OPEN_REPLS, repl);
        return repl;
    }

    public void reset(@NonNull Memory memory) {
        final List<Object> repls = memory.getList(SYM_OPEN_REPLS);
        if (repls == null) { return; }

        for (Object repl: repls) {
            if (!(repl instanceof Replicator)) {
                Log.e(TAG, "Attempt to close non-replicator: " + repl);
                continue;
            }

            ((Replicator) repl).stop();
        }
    }
}
