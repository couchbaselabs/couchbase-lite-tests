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
import com.couchbase.lite.mobiletest.endpoints.v1.PerformMaintenance;
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
        Map<String, Object> run(@Nullable TestContext ctxt, @NonNull TypedMap req);
    }

    public PostDispatcher(@NonNull TestApp app) {
        super(app);

        // build the dispatch table
        addEndpoint(1, "/reset", (c, r) -> new Reset(app).reset(c, r));
        addEndpoint(1, "/startTest", (c, r) -> new Reset(app).startTest(c, r));
        addEndpoint(1, "/endTest", (c, r) -> new Reset(app).endTest(c, r));
        addEndpoint(1, "/getAllDocuments", (c, r) -> new GetAllDocs(app.getDbSvc()).getAllDocs(c, r));
        addEndpoint(1, "/updateDatabase", (c, r) -> new UpdateDb(app.getDbSvc()).updateDb(c, r));
        addEndpoint(1, "/startReplicator", (c, r) -> new CreateRepl(app.getDbSvc(), app.getReplSvc()).createRepl(c, r));
        addEndpoint(1, "/getReplicatorStatus", (c, r) -> new GetReplStatus(app.getReplSvc()).getReplStatus(c, r));
        addEndpoint(1, "/snapshotDocuments", (c, r) -> new SnapshotDocs(app.getDbSvc()).snapshot(c, r));
        addEndpoint(1, "/verifyDocuments", (c, r) -> new VerifyDocs(app.getDbSvc()).verify(c, r));
        addEndpoint(1, "/performMaintenance", (c, r) -> new PerformMaintenance(app.getDbSvc()).doMaintenance(c, r));
    }

    // This method returns a Reply.  Be sure to close it!
    @NonNull
    public Reply handleRequest(
        @Nullable String client,
        int version,
        @NonNull String path,
        @Nullable String contentType,
        @NonNull InputStream request
    ) throws IOException {
        if (version < 0) { throw new ClientError("No protocol version specified"); }
        if (client == null) { throw new ClientError("No client specified"); }
        if (!TestApp.CONTENT_TYPE_JSON.equalsIgnoreCase(contentType)) {
            throw new ClientError("Content type should be '" + TestApp.CONTENT_TYPE_JSON + " but is " + contentType);
        }

        final Endpoint endpoint = getEndpoint(version, path);
        if (endpoint == null) {
            final String msg = "Unrecognized post request: " + path + " v" + version;
            Log.w(TAG, msg);
            throw new ClientError(msg);
        }

        final TypedMap req = new RequestBuilder(request).buildRequest();
        final TestContext ctxt = TestApp.getApp().getTestContext(client);
        if (ctxt == null) { req.put(Reset.KEY_CLIENT, client); }

        final Map<String, Object> result = endpoint.run(ctxt, req);

        Log.w(TAG, "Request succeeded");
        return new Reply(new ReplyBuilder(result).buildReply());
    }
}

