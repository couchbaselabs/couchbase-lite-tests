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

import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.LogService;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.Log;


public class Logger {
    private static final String KEY_MESSAGE = "message";

    private static final String KEY_URL = "url";
    private static final String KEY_ID = "id";
    private static final String KEY_TAG = "tag";

    private static final Set<String> LEGAL_LOG_KEYS;
    private final LogService logSvc;


    public Logger(@NonNull LogService logSvc) { this.logSvc = logSvc; }

    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_MESSAGE);
        LEGAL_LOG_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_SETUP_LOGGING_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_URL);
        l.add(KEY_ID);
        l.add(KEY_TAG);
        LEGAL_SETUP_LOGGING_KEYS = Collections.unmodifiableSet(l);
    }

    /* log a message from the client */
    @NonNull
    public Map<String, Object> log(@NonNull TypedMap req) {
        req.validate(LEGAL_LOG_KEYS);

        final String msg = req.getString(KEY_MESSAGE);
        Log.p("CLIENT", (msg == null) ? "" : msg);

        return Collections.emptyMap();
    }

    @NonNull
    public Map<String, Object> setupLogging(@NonNull TypedMap req) {
        req.validate(LEGAL_SETUP_LOGGING_KEYS);

        final String url = req.getString(KEY_URL);
        if (url == null) { throw new ClientError("No log slurper URL in setupLogging"); }

        final String id = req.getString(KEY_ID);
        if (id == null) { throw new ClientError("No server id in setupLogging"); }

        final String tag = req.getString(KEY_URL);
        if (tag == null) { throw new ClientError("No log tag in setupLogging"); }

        logSvc.setupLogging(url, id, tag);

        return Collections.emptyMap();
    }
}
