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
package com.couchbase.lite.mobiletest.endpoints.v1;

import androidx.annotation.NonNull;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.ListenerService;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TypedMap;

public class ListenerManager {
    @NonNull
    private final DatabaseService dbSvc;
    @NonNull
    private final ListenerService listenerSvc;

    public ListenerManager(@NonNull DatabaseService dbSvc, @NonNull ListenerService listenerSvc) {
        this.dbSvc = dbSvc;
        this.listenerSvc = listenerSvc;
    }

    @NonNull
    public Map<String, Object> createListener(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        // TODO: Implement

        final Map<String, Object> ret = new HashMap<>();
        return ret;
    }

    @NonNull
    public Map<String, Object> stopListener(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        // TODO: Implement

        return Collections.emptyMap();
    }
}
