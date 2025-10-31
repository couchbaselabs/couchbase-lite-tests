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

import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.MultipeerReplicator;
import com.couchbase.lite.android.mobiletest.AndroidTestApp;
import com.couchbase.lite.mobiletest.endpoints.v1.Session;
import com.couchbase.lite.mobiletest.errors.ClientError;


public final class TestContext extends BaseTestContext {

    @Nullable
    private Map<String, MultipeerReplicator> openMultipeerRepls;

    public TestContext(@NonNull TestApp app, @NonNull Session session, @NonNull String testName) {
        super(app, session, testName);
    }

    @NonNull
    @Override
    protected TestContext getTestContext() { return this; }

    public void addMultipeerRepl(@NonNull String id, @NonNull MultipeerReplicator multipeerRepl) {
        Map<String, MultipeerReplicator> multipeerRepls = openMultipeerRepls;
        if (multipeerRepls == null) {
            multipeerRepls = new HashMap<>();
            openMultipeerRepls = multipeerRepls;
        }
        if (openMultipeerRepls.containsKey(id)) {
            throw new ClientError("Attempt to replace an existing multipeer replicator");
        }
        multipeerRepls.put(id, multipeerRepl);
    }

    @Nullable
    public MultipeerReplicator getMultipeerRepl(@NonNull String id) {
        final Map<String, MultipeerReplicator> multipeerRepls = openMultipeerRepls;
        return (multipeerRepls == null) ? null : multipeerRepls.get(id);
    }

    @Nullable
    public MultipeerReplicator removeMultipeerRepl(@NonNull String id) {
        final Map<String, MultipeerReplicator> multipeerRepls = openMultipeerRepls;
        return (multipeerRepls == null) ? null : multipeerRepls.remove(id);
    }

    public void close(@NonNull TestApp app) {
        ((AndroidTestApp) app).clearMultipeerReplSvc();
        stopMultipeerRepls();
        super.close(app);
    }

    private void stopMultipeerRepls() {
        final Map<String, MultipeerReplicator> liveRepls = openMultipeerRepls;
        openMultipeerRepls = null;
        if (liveRepls == null) { return; }
        for (MultipeerReplicator repl: liveRepls.values()) {
            if (repl != null) { repl.stop(); }
        }
    }
}
