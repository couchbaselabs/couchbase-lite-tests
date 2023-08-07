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

import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.endpoints.CreateReplV1;
import com.couchbase.lite.mobiletest.endpoints.GetAllDocsV1;
import com.couchbase.lite.mobiletest.endpoints.GetReplStatusV1;
import com.couchbase.lite.mobiletest.endpoints.ResetV1;
import com.couchbase.lite.mobiletest.endpoints.UpdateDbV1;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.tools.ReplyBuilder;
import com.couchbase.lite.mobiletest.tools.RequestBuilder;
import com.couchbase.lite.mobiletest.util.Log;


public final class Dispatcher {
    private static final String TAG = "DISPATCH";

    public enum Method {GET, PUT, POST, DELETE}

    @FunctionalInterface
    interface Endpoint {
        @NonNull
        Map<String, Object> run(@NonNull TypedMap req, @NonNull Memory mem);
    }

    private final Map<Integer, Map<String, Map<Method, Endpoint>>> dispatchTable = new HashMap<>();
    private final TestApp app;

    public Dispatcher(@NonNull TestApp app) { this.app = app; }

    // build the dispatch table
    public void init() {
        addEndpoint(1, "/", Method.GET, (r, m) -> app.getSystemInfo());
        addEndpoint(1, "/reset", Method.POST, (r, m) -> new ResetV1(app).reset(r, m));
        addEndpoint(1, "/getAllDocuments", Method.POST, (r, m) -> new GetAllDocsV1(app.getDbSvc()).getAllDocs(r, m));
        addEndpoint(1, "/updateDatabase", Method.POST, (r, m) -> new UpdateDbV1(app.getDbSvc()).updateDb(r, m));
        addEndpoint(1, "/startReplicator", Method.POST, (r, m) -> new CreateReplV1(app.getReplSvc()).createRepl(r, m));
        addEndpoint(
            1,
            "/getReplicatorStatus",
            Method.POST,
            (r, m) -> new GetReplStatusV1(app.getReplSvc()).getReplStatus(r, m));
        addEndpoint(1, "/snapshotDocuments", Method.POST, (r, m) -> Collections.emptyMap());
        addEndpoint(1, "/verifyDocuments", Method.POST, (r, m) -> Collections.emptyMap());
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
        final Endpoint endpoint = getEndpoint(version, path, method);
        if (endpoint == null) {
            final String msg = "Unrecognized request: " + method + " " + path + " @" + version;
            Log.w(TAG, msg);
            throw new ClientError(msg);
        }

        final Map<String, Object> result = endpoint.run(
            new RequestBuilder(req).buildRequest(),
            TestApp.getApp().getMemory(client));

        Log.w(TAG, "Request succeeded");
        return new Reply(new ReplyBuilder(result).buildReply());
    }

    @Nullable
    private Endpoint getEndpoint(int version, @NonNull String path, @NonNull Method method) {
        final Map<String, Map<Method, Endpoint>> vMap = dispatchTable.get(version);
        if (vMap != null) {
            final Map<Method, Endpoint> veMap = vMap.get(path);
            if (veMap != null) { return veMap.get(method); }
        }
        return null;
    }

    private void addEndpoint(int version, @NonNull String path, @NonNull Method method, @NonNull Endpoint action) {
        final Map<String, Map<Method, Endpoint>> vMap = dispatchTable.computeIfAbsent(version, k -> new HashMap<>());
        final Map<Method, Endpoint> veMap = vMap.computeIfAbsent(path, k -> new HashMap<>());
        if (veMap.get(method) != null) { Log.w(TAG, "Replacing method: " + path + "@" + method + " v" + version); }
        veMap.put(method, action);
    }
}

