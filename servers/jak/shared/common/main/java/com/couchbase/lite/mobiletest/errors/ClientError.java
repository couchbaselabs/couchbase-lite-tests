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


// Use this to report a bad client request
public class ClientError extends TestError {
    @NonNull
    private final HTTPStatus status;

    public ClientError(@NonNull String message) { this(message, null); }

    public ClientError(@NonNull HTTPStatus status, @NonNull String message) { this(status, message, null); }

    public ClientError(@NonNull String message, @Nullable Throwable cause) {
        this(HTTPStatus.BAD_REQUEST, message, cause);
    }

    public ClientError(@NonNull HTTPStatus status, @NonNull String message, @Nullable Throwable cause) {
        super(DOMAIN_TESTSERVER, status.getCode(), message, cause);
        this.status = status;
    }

    @NonNull
    public HTTPStatus getStatus() { return status; }
}
