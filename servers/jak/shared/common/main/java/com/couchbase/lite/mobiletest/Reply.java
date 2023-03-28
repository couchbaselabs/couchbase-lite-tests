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

import okio.Buffer;


public class Reply implements AutoCloseable {
    public enum Status {
        OK(200), BAD_REQUEST(400), METHOD_NOT_ALLOWED(405);

        private final int code;

        Status(int code) { this.code = code; }

        public int getCode() { return code; }
    }

    @NonNull
    private final Status status;
    @NonNull
    private final String contentType;
    @NonNull
    private final Buffer content;

    public Reply(@NonNull Status code, @NonNull String contentType, @NonNull Buffer content) {
        this.status = code;
        this.contentType = contentType;
        this.content = content;
    }

    @NonNull
    public String getContentType() { return contentType; }

    @NonNull
    public Status getStatus() { return status; }

    @NonNull
    public InputStream getContent() {
        if (!content.isOpen()) { throw new IllegalStateException("Attempt to get reply content after close"); }
        return content.inputStream();
    }

    public long getSize() {
        if (!content.isOpen()) { throw new IllegalStateException("Attempt to get reply size after close"); }
        return content.size();
    }

    @Override
    public void close() { content.close(); }
}
