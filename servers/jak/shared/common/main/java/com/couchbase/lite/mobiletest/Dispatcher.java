//
// Copyright (c) 2022 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.IOException;
import java.io.InputStream;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.tools.DbUpdater;
import com.couchbase.lite.mobiletest.tools.ReplyBuilder;
import com.couchbase.lite.mobiletest.tools.RequestBuilder;
import com.couchbase.lite.mobiletest.util.Log;


public final class Dispatcher {
    private static final String TAG = "DISPATCH";

    public enum Method {GET, PUT, POST, DELETE}

    private final Map<Integer, Map<String, Map<Method, Test>>> dispatchTable = new HashMap<>();
    private final TestApp app;

    public Dispatcher(@NonNull TestApp app) { this.app = app; }

    // build the dispatch table
    public void init() {
        addTest(1, "/", Method.GET, (r, m) -> app.getSystemInfo());
        addTest(1, "/reset", Method.POST, app::reset);
        addTest(1, "/getAllDocuments", Method.POST, (r, m) -> app.getDbSvc().getAllDocsV1(r, m));
        addTest(1, "/updateDatabase", Method.POST, (r, m) -> new DbUpdater(app.getDbSvc()).updateDbV1(r, m));
        addTest(1, "/startReplicator", Method.POST, (r, m) -> app.getReplSvc().createReplV1(r, m));
        addTest(1, "/getReplicatorStatus", Method.POST, (r, m) -> app.getReplSvc().getReplStatusV1(r, m));
        addTest(1, "/snapshotDocuments", Method.POST, (r, m) -> Collections.emptyMap());
        addTest(1, "/verifyDocuments", Method.POST, (r, m) -> Collections.emptyMap());
    }

    // This method returns a Reply.  Be sure to close it!
    @NonNull
    public Reply handleRequest(
        @NonNull String client,
        int version,
        @NonNull Dispatcher.Method method,
        @NonNull String path,
        @NonNull InputStream req
    ) throws IOException {
        final Test test = getTest(version, path, method);
        if (test == null) {
            final String msg = "Unrecognized request: " + method + " " + path + " @" + version;
            Log.w(TAG, msg);
            throw new ClientError(msg);
        }

        final Map<String, Object> result = test.run(
            new RequestBuilder(req).buildRequest(),
            TestApp.getApp().getMemory(client));

        Log.w(TAG, "Request succeeded");
        return new Reply(new ReplyBuilder(result).buildReply());
    }

    @Nullable
    private Test getTest(int version, @NonNull String path, @NonNull Method method) {
        final Map<String, Map<Method, Test>> vMap = dispatchTable.get(version);
        if (vMap != null) {
            final Map<Method, Test> veMap = vMap.get(path);
            if (veMap != null) { return veMap.get(method); }
        }
        return null;
    }

    private void addTest(int version, @NonNull String path, @NonNull Method method, @NonNull Test action) {
        Map<String, Map<Method, Test>> vMap = dispatchTable.get(version);
        if (vMap == null) {
            vMap = new HashMap<>();
            dispatchTable.put(version, vMap);
        }
        Map<Method, Test> veMap = vMap.get(path);
        if (veMap == null) {
            veMap = new HashMap<>();
            vMap.put(path, veMap);
        }
        if (veMap.get(method) != null) {
            Log.w(TAG, "Replacing method: " + path + "@" + method + " v" + version);
        }
        veMap.put(method, action);
    }
}

