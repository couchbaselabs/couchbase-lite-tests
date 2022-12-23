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

import java.util.HashMap;
import java.util.Map;

import org.jetbrains.annotations.NotNull;


public final class Dispatcher {
    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @FunctionalInterface
    private interface Action {
        @NonNull
        Reply run(@NonNull Args args, @NonNull Memory mem) throws Exception;
    }

    private final Map<String, Action> dispatchTable = new HashMap<>();

    public void init() { dispatchTable.put("version", (args, mem) -> Reply.from(TestApp.getApp().getAppVersion())); }

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @NonNull
    public Reply run(@NonNull String method, @NotNull Args args, @NonNull Memory mem) throws Exception {
        final Action action = dispatchTable.get(method);
        if (action == null) { throw new IllegalArgumentException("No such method: " + method); }
        return action.run(args, mem);
    }
}

