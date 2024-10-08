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
package com.couchbase.lite.mobiletest.errors;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;


// The base class for TestServer errors
public class TestError extends RuntimeException {
    protected static final String DOMAIN_TESTSERVER = "TESTSERVER";

    @NonNull
    private final String domain;
    private final int code;

    public TestError(@NonNull String domain, int code, @NonNull String message) {
        super(message);
        this.domain = domain;
        this.code = code;
    }

    public TestError(@NonNull String domain, int code, @NonNull String message, @Nullable Throwable cause) {
        super(message, cause);
        this.domain = domain;
        this.code = code;
    }

    @NonNull
    public String getDomain() { return domain; }

    public int getCode() { return code; }
}
