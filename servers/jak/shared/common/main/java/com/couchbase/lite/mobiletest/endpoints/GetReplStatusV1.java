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

import java.util.Collections;
import java.util.Map;

import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorStatus;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.ReplicatorService;
import com.couchbase.lite.mobiletest.tools.ReplicatorStatusBuilder;
import com.couchbase.lite.mobiletest.util.Log;


public class GetReplStatusV1 {
    private static final String TAG = "REPL_STATUS_V1";

    private static final String KEY_REPL_ID = "id";

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

        // !!! Need to supply the list of document replications
        return new ReplicatorStatusBuilder(replStatus, Collections.emptyList()).build();
    }
}
