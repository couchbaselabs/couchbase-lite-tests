//
// Copyright (c) 2024 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.mobiletest.errors.ServerError;

@SuppressWarnings({"PMD.UnusedPrivateField", "PMD.SingularField"})
public class RemoteLogger extends Log.TestLogger {
    @NonNull
    private final String id;
    @NonNull
    private final String tag;
    @NonNull
    private final String url;

    public RemoteLogger(@NonNull String id, @NonNull String tag, @NonNull String url) {
        this.id = id;
        this.tag = tag;
        this.url = url;
    }

    @Override
    public void log(@NonNull LogLevel level, @NonNull LogDomain domain, @NonNull String msg) {
        log(level, domain.toString(), msg, null);
    }

    @Override
    public void log(LogLevel level, String tag, String msg, Exception err) {
        throw new ServerError("not het implemented");
    }

    @Override
    public void close() { throw new ServerError("not het implemented"); }

    public void connect() { throw new ServerError("not het implemented"); }
}
