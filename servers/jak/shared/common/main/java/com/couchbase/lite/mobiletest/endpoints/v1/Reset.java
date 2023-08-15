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
import java.util.Map;

import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.data.TypedMap;


public class Reset {
    @NonNull
    private final TestApp app;

    public Reset(@NonNull TestApp app) { this.app = app; }

    @NonNull
    public final Map<String, Object> reset(@NonNull TypedMap req, @NonNull TestContext ctxt) {
        final String client = ctxt.getClient();

        app.clearReplSvc();
        app.clearDbSvc();
        ctxt.close();

        final TestContext newCtxt = app.resetContext(client);
        app.getDbSvc().init(req, newCtxt);
        app.getReplSvc().init(req, newCtxt);

        return Collections.emptyMap();
    }
}

