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
package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.mobiletest.util.Log;


public class BaseDispatcher<T> {
    private static final String TAG = "DISPATCH";

    @NonNull
    private final Map<Integer, Map<String, T>> dispatchTable = new HashMap<>();

    @NonNull
    protected final TestApp app;

    public BaseDispatcher(@NonNull TestApp app) { this.app = app; }

    @Nullable
    protected T getEndpoint(int version, @NonNull String path) {
        final Map<String, T> endpoints = dispatchTable.get(version);
        return (endpoints == null) ? null : endpoints.get(path);
    }

    protected void addEndpoint(int version, @NonNull String path, @NonNull T action) {
        final Map<String, T> endpoints = dispatchTable.computeIfAbsent(version, k -> new HashMap<>());
        if (endpoints.containsKey(path)) { Log.w(TAG, "Replacing endpoint: " + path + " v" + version); }
        endpoints.put(path, action);
    }
}
