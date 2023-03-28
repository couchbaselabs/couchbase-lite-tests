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
package com.couchbase.lite.mobiletest.json;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.squareup.moshi.JsonReader;
import com.squareup.moshi.JsonWriter;
import okio.Buffer;
import okio.Okio;

import com.couchbase.lite.mobiletest.Memory;


public final class JsonV1 extends Json {
    @SuppressWarnings("PMD.PrematureDeclaration")
    @NonNull
    public Map<String, Object> parseRequest(@NonNull InputStream json) throws IOException {
        final JsonReader reader = JsonReader.of(Okio.buffer(Okio.source(json)));
        final Map<String, Object> val = parseMap(reader);
        if (reader.hasNext()) { throw new IOException("Unexpected content after document end"); }
        return val;
    }

    @NonNull
    public Buffer serializeReply(@Nullable Map<String, Object> data) throws IOException {
        final Buffer buf = new Buffer();
        final JsonWriter writer = JsonWriter.of(buf);
        writer.setLenient(true);
        writer.setSerializeNulls(true);
        serializeMap((data != null) ? data : new HashMap<String, Object>(), writer);
        return buf;
    }

    @Nullable
    protected Object parseString(@NonNull String s) {
        switch (s) {
            case "null":
                return null;
            case "true":
                return true;
            case "false":
                return false;
            default:
                return getRef(s);
        }
    }

    @SuppressWarnings("PMD.PrematureDeclaration")
    @NonNull
    private Object getRef(@NonNull String s) {
        final String suffix = s.substring(1);
        switch (s.substring(0, 1)) {
            case "I":
                return Integer.valueOf(suffix);
            case "L":
                return Long.valueOf(suffix);
            case "F":
                return Float.valueOf(suffix);
            case "D":
                return Double.valueOf(suffix);
            case "\"":
                return !suffix.endsWith("\"") ? s : suffix.substring(0, suffix.length() - 1);
            case "@":
                return new Memory.Ref(suffix);
            default:
                return s;
        }
    }

    @SuppressWarnings("PMD.NPathComplexity")
    protected void serializeValue(@Nullable Object value, @NonNull JsonWriter writer) throws IOException {
        if ((value == null) || ("null".equals(value))) {
            writer.value("null");
            return;
        }
        if (value instanceof Boolean) {
            writer.value(((Boolean) value) ? "true" : "false");
            return;
        }
        if (value instanceof Integer) {
            writer.value("I" + value);
            return;
        }
        if (value instanceof Long) {
            writer.value("L" + value);
            return;
        }
        if (value instanceof Float) {
            writer.value("F" + value);
            return;
        }
        if (value instanceof Double) {
            writer.value("D" + value);
            return;
        }
        if (value instanceof String) {
            writer.value("\"" + value + "\"");
            return;
        }
        if (value instanceof Memory.Ref) {
            writer.value(Memory.PREFIX_REF + ((Memory.Ref) value).key);
            return;
        }
        if (value instanceof List) {
            serializeList((List<?>) value, writer);
            return;
        }
        if (value instanceof Map) {
            serializeMap((Map<?, ?>) value, writer);
            return;
        }

        throw new IllegalArgumentException("Value not a serializable type: " + value);
    }
}
