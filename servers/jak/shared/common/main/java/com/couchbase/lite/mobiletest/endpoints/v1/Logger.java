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
package com.couchbase.lite.mobiletest.endpoints.v1;

import androidx.annotation.NonNull;

import java.util.Collections;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public class Logger {
    private static final String KEY_MESSAGE = "message";

    private static final Set<String> LEGAL_LOG_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_MESSAGE);
        LEGAL_LOG_KEYS = Collections.unmodifiableSet(l);
    }

    /* log a message from the client */
    @NonNull
    public Map<String, Object> log(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_LOG_KEYS);

        final String msg = req.getString(KEY_MESSAGE);
        Log.p("CLIENT", (msg == null) ? "" : msg);

        return Collections.emptyMap();
    }
}
