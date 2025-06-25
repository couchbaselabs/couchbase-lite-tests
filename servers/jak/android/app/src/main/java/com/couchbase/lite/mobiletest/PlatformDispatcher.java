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
package com.couchbase.lite.mobiletest;

import com.couchbase.lite.android.mobiletest.AndroidTestApp;
import com.couchbase.lite.android.mobiletest.endpoints.v1.MultipeerReplicatorManager;


final class PlatformDispatcher {
    private PlatformDispatcher() {
        // Prevent instantiation
    }

    public static void addGetEndpoints(GetDispatcher dispatcher, TestApp app) {
        // there are no Android-specific GET endpoints
    }

    public static void addPostEndpoints(PostDispatcher dispatcher, TestApp app) {
        final AndroidTestApp androidApp = (AndroidTestApp) app;
        dispatcher.addEndpoint(
            1,
            "/startMultipeerReplicator",
            (c, r) -> new MultipeerReplicatorManager(app.getDbSvc(), androidApp.getMultipeerReplSvc())
                .createRepl(app.getTestContext(c), r));
        dispatcher.addEndpoint(
            1,
            "/getMultipeerReplicatorStatus",
            (c, r) -> new MultipeerReplicatorManager(app.getDbSvc(), androidApp.getMultipeerReplSvc())
                .getReplStatus(app.getTestContext(c), r));
        dispatcher.addEndpoint(
            1,
            "/stopMultipeerReplicator",
            (c, r) -> new MultipeerReplicatorManager(app.getDbSvc(), androidApp.getMultipeerReplSvc())
                .stopRepl(app.getTestContext(c), r));
    }
}
