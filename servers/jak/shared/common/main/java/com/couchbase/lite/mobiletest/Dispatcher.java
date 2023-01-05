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

import java.io.InputStream;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.atomic.AtomicReference;

import org.jetbrains.annotations.NotNull;

import com.couchbase.lite.mobiletest.util.Log;


public final class Dispatcher {
    private static final String TAG = "DISPATCH";

    public enum Method {GET, PUT, POST, DELETE}

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @FunctionalInterface
    private interface Action {
        void run(@NonNull Task task, @NonNull HashMap<String, Object> reply, @NonNull Memory mem) throws Exception;
    }


    private final Memory memory;

    private final Map<String, Action> dispatchTable = new HashMap<>();

    private final AtomicReference<String> client = new AtomicReference<>();

    public Dispatcher(TestApp app) { memory = Memory.create(app); }

    // build the dispatch table
    public void init() {
        dispatchTable.put("get@version", (task, reply, mem) -> reply.put("version", TestApp.getApp().getAppVersion()));
    }

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @NonNull
    public Reply run(
        int version,
        @NonNull String client,
        @NonNull Method method,
        @NonNull String request,
        @NotNull InputStream data) throws Exception {
        final String previousClient = this.client.getAndSet(client);
        if (!client.equals(previousClient)) { Log.w(TAG, "New client: " + previousClient + " >>> " + client); }

        final String act = (method + "@" + request).toLowerCase(Locale.getDefault());
        final Action action = dispatchTable.get(act);
        if (action == null) { throw new IllegalArgumentException("Unrecognized request: " + act); }

        final HashMap<String, Object> reply = new HashMap<>();
        action.run(Task.from(version, data), reply, memory);

        return Reply.from(reply);
    }
}

