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
package com.couchbase.lite.mobiletest.json;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.IOException;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.squareup.moshi.JsonWriter;
import okio.Buffer;

import com.couchbase.lite.Blob;
import com.couchbase.lite.mobiletest.errors.ServerError;


public class ReplyBuilder {
    private final Map<String, Object> reply;

    public ReplyBuilder(@Nullable Map<String, Object> reply) { this.reply = reply; }

    @NonNull
    public Buffer buildReply() throws IOException {
        final Buffer buf = new Buffer();
        final JsonWriter writer = JsonWriter.of(buf);
        writer.setLenient(true);
        writer.setSerializeNulls(true);
        serializeMap((reply != null) ? reply : new HashMap<String, Object>(), writer);
        return buf;
    }

    private void serializeMap(Map<?, ?> value, @NonNull JsonWriter writer) throws IOException {
        writer.beginObject();
        for (Map.Entry<?, ?> entry: value.entrySet()) {
            final Object key = entry.getKey();
            if (!(key instanceof String)) {
                throw new ServerError("Key is not a string in serialize: " + key);
            }
            writer.name((String) key);
            serializeValue(entry.getValue(), writer);
        }
        writer.endObject();
    }

    private void serializeList(List<?> value, @NonNull JsonWriter writer) throws IOException {
        writer.beginArray();
        for (Object item: value) { serializeValue(item, writer); }
        writer.endArray();
    }

    private void serializeValue(@Nullable Object value, @NonNull JsonWriter writer) throws IOException {
        if (value == null) {
            writer.nullValue();
            return;
        }
        if (value instanceof Boolean) {
            writer.value((Boolean) value);
            return;
        }
        if (value instanceof Number) {
            writer.value((Number) value);
            return;
        }
        if (value instanceof String) {
            writer.value((String) value);
            return;
        }
        if (value instanceof Blob) {
            final Map<String, Object> blob = ((Blob) value).getProperties();
            blob.put("@type", "blob");
            serializeMap(blob, writer);
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

        throw new ServerError("Value not a serializable type: " + value + " (" + value.getClass().getCanonicalName());
    }
}


