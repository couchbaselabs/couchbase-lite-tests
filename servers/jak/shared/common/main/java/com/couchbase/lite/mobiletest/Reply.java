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

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import okio.Buffer;

import com.couchbase.lite.mobiletest.util.Json;


public final class Reply {
    public static final Reply EMPTY = from("I-1");

    @NonNull
    public static Reply from(@NonNull String str) {
        final String data = '"' + str + '"';
        return Reply.from("text/plain", data.getBytes(StandardCharsets.UTF_8));
    }

    @NonNull
    public static Reply from(@NonNull String contentType, @NonNull byte[] data) {
        return new Reply(contentType, new ByteArrayInputStream(data), data.length);
    }

    @NonNull
    public static Reply from(@Nullable Object data) throws IOException {
        final Buffer buf = new Json().serialize(data);
        return new Reply("application/json", buf.inputStream(), buf.size());
    }

    private final String contentType;
    private final InputStream data;
    private final long size;

    public Reply(@NonNull String contentType, @NonNull InputStream data, long size) {
        this.contentType = contentType;
        this.data = data;
        this.size = size;
    }

    @NonNull
    public String getContentType() { return contentType; }

    public InputStream getData() { return data; }

    public long size() { return size; }
}
