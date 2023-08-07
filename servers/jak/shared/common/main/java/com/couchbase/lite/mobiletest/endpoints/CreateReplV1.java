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

import java.util.HashMap;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.Replicator;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.services.ReplicatorService;
import com.couchbase.lite.mobiletest.tools.ReplicatorConfigBuilder;
import com.couchbase.lite.mobiletest.util.Log;


public class CreateReplV1 {
    private static final String TAG = "CREATE_REPL_V1";

    private static final String KEY_REPL_ID = "id";


    @NonNull
    private final ReplicatorService replSvc;

    public CreateReplV1(@NonNull ReplicatorService replSvc) { this.replSvc = replSvc; }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @NonNull
    public Map<String, Object> createRepl(@NonNull TypedMap req, @NonNull Memory mem) {
        final ReplicatorConfigBuilder configBuilder = new ReplicatorConfigBuilder(req, mem);
        final Replicator repl = new Replicator(configBuilder.build());
        final String replId = replSvc.addRepl(mem, repl);

        repl.start(configBuilder.shouldReset());
        Log.i(TAG, "Started replicator: " + replId);

        final Map<String, Object> ret = new HashMap<>();
        ret.put(KEY_REPL_ID, replId);
        return ret;
    }
}
