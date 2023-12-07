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
import java.util.Map;

import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.json.ReplyBuilder;
import com.couchbase.lite.mobiletest.util.Log;


public final class GetDispatcher extends BaseDispatcher<GetDispatcher.Endpoint> {
    private static final String TAG = "GET";

    @FunctionalInterface
    interface Endpoint {
        @NonNull
        Map<String, Object> run(@NonNull TestContext ctxt);
    }

    public GetDispatcher(@NonNull TestApp app) {
        super(app);

        // build the endpoint table
        addEndpoint(1, "/", (m) -> app.getSystemInfo());
    }

    // This method returns a Reply.  Be sure to close it!
    @NonNull
    public Reply handleRequest(@Nullable String client, int version, @NonNull String path) throws IOException {
        // Special handling for the '/' endpoint
        if ("/".equals(path)) {
            if (version < 0) { version = TestApp.LATEST_SUPPORTED_PROTOCOL_VERSION; }
            if (client == null) { client = "anonymous"; }
        }
        if (version < 0) { throw new ClientError("No protocol version specified"); }
        if (client == null) { throw new ClientError("No client specified"); }

        final Endpoint endpoint = getEndpoint(version, path);
        if (endpoint == null) {
            final String msg = "Unrecognized get request: " + path + " v" + version;
            Log.err(TAG, msg);
            throw new ClientError(msg);
        }

        final Map<String, Object> result = endpoint.run(TestApp.getApp().getTestContext(client));

        Log.p(TAG, "Request succeeded");
        return new Reply(new ReplyBuilder(result).buildReply());
    }
}
