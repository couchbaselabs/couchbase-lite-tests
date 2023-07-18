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
package com.couchbase.lite.mobiletest.serializers.v1;

import androidx.annotation.NonNull;

import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.ReplicatorProgress;
import com.couchbase.lite.ReplicatorStatus;


public class ReplicatorStatusBuilder {
    private static final String KEY_REPL_ACTIVITY = "'activity'";
    private static final String KEY_REPL_PROGRESS = "'progress'";
    private static final String KEY_REPL_DOCS_COMPLETE = "complete";
    private static final String KEY_REPL_DOC_COUNT = "documentCount";

    @NonNull
    ReplicatorStatus replStatus;

    public ReplicatorStatusBuilder(@NonNull ReplicatorStatus replStatus) {
        this.replStatus = replStatus;
    }

    @NonNull
    public Map<String, Object> build() {
        final Map<String, Object> progress = new HashMap<>();
        final ReplicatorProgress replProgress = replStatus.getProgress();
        progress.put(KEY_REPL_DOC_COUNT, replProgress.getTotal());
        progress.put(KEY_REPL_DOCS_COMPLETE, replProgress.getCompleted());

        final Map<String, Object> resp = new HashMap<>();
        resp.put(KEY_REPL_PROGRESS, progress);
        resp.put(KEY_REPL_ACTIVITY, replStatus.getActivityLevel().toString());

        // !!! This needs to handle the "documents" key

        return resp;
    }
}
