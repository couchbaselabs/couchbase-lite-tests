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
import java.util.Map;

import com.couchbase.lite.mobiletest.endpoints.v1.CreateRepl;
import com.couchbase.lite.mobiletest.endpoints.v1.GetAllDocs;
import com.couchbase.lite.mobiletest.endpoints.v1.GetReplStatus;
import com.couchbase.lite.mobiletest.endpoints.v1.Reset;
import com.couchbase.lite.mobiletest.endpoints.v1.SnapshotDocs;
import com.couchbase.lite.mobiletest.endpoints.v1.UpdateDb;
import com.couchbase.lite.mobiletest.endpoints.v1.VerifyDocs;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.json.ReplyBuilder;
import com.couchbase.lite.mobiletest.json.RequestBuilder;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.Log;


public final class PostDispatcher extends BaseDispatcher<PostDispatcher.Endpoint> {
    private static final String TAG = "POST";

    @FunctionalInterface
    interface Endpoint {
        @NonNull
        Map<String, Object> run(@NonNull TypedMap req, @NonNull TestContext ctxt);
    }

    public PostDispatcher(@NonNull TestApp app) {
        super(app);

        // build the dispatch table
        addEndpoint(1, "/reset", (r, m) -> new Reset(app).reset(r, m));
        addEndpoint(1, "/getAllDocuments", (r, m) -> new GetAllDocs(app.getDbSvc()).getAllDocs(r, m));
        addEndpoint(1, "/updateDatabase", (r, m) -> new UpdateDb(app.getDbSvc()).updateDb(r, m));
        addEndpoint(1, "/startReplicator", (r, m) -> new CreateRepl(app.getDbSvc(), app.getReplSvc()).createRepl(r, m));
        addEndpoint(1, "/getReplicatorStatus", (r, m) -> new GetReplStatus(app.getReplSvc()).getReplStatus(r, m));
        addEndpoint(1, "/snapshotDocuments", (r, m) -> new SnapshotDocs(app.getDbSvc()).snapshot(r, m));
        addEndpoint(1, "/verifyDocuments", (r, m) -> new VerifyDocs(app.getDbSvc()).verify(r, m));
    }

    // This method returns a Reply.  Be sure to close it!
    @NonNull
    public Reply handleRequest(
        @Nullable String client,
        int version,
        @NonNull String path,
        @NonNull InputStream req
    ) throws IOException {
        if (version < 0) { throw new ClientError("No protocol version specified"); }
        if (client == null) { throw new ClientError("No client specified"); }

        final Endpoint endpoint = getEndpoint(version, path);
        if (endpoint == null) {
            final String msg = "Unrecognized post request: " + path + " v" + version;
            Log.w(TAG, msg);
            throw new ClientError(msg);
        }

        final Map<String, Object> result
            = endpoint.run(new RequestBuilder(req).buildRequest(), TestApp.getApp().getTestContext(client));

        Log.w(TAG, "Request succeeded");
        return new Reply(new ReplyBuilder(result).buildReply());
    }
}

