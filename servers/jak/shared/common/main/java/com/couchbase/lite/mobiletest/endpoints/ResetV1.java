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

import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.ReplicatorService;


public class ResetV1 {
    @NonNull
    private final TestApp app;

    public ResetV1(@NonNull TestApp app) { this.app = app; }

    @NonNull
    public final Map<String, Object> reset(@NonNull TypedMap req, @NonNull Memory mem) {
        final ReplicatorService rMgr = app.clearReplSvc();
        if (rMgr != null) { rMgr.reset(mem); }

        final DatabaseService dMgr = app.clearDbSvc();
        if (dMgr != null) { dMgr.reset(mem); }

        final Memory newMem = app.clearMemory(mem.getClient());

        app.getDbSvc().init(req, newMem);

        app.getReplSvc();

        return Collections.emptyMap();
    }
}

