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
package com.couchbase.lite.mobiletest.util;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.squareup.moshi.JsonReader;
import com.squareup.moshi.JsonWriter;
import okio.Buffer;
import okio.Okio;

import com.couchbase.lite.mobiletest.Memory;


public final class Json {
    public <T> T parse(@NonNull InputStream in, Class<T> requiredType) throws IOException {
        final JsonReader json = JsonReader.of(Okio.buffer(Okio.source(in)));

        if (json.peek() == JsonReader.Token.END_DOCUMENT) { return null; }

        final Object val = parseValue(json);

        if (json.peek() != JsonReader.Token.END_DOCUMENT) {
            throw new IOException("Unexpected content after document end");
        }

        if (val == null) { return null; }

        return requiredType.cast(val);
    }

    public Buffer serialize(@Nullable Object value) throws IOException {
        Buffer buf = new Buffer();
        JsonWriter writer = JsonWriter.of(buf);
        writer.setLenient(true);
        writer.setSerializeNulls(true);
        serializeValue(value, writer);
        return buf;
    }


    @NonNull
    private Map<String, Object> parseMap(@NonNull JsonReader json) throws IOException {
        json.beginObject();
        final Map<String, Object> map = new HashMap<>();
        while (json.hasNext()) {
            final String key = json.nextName();
            map.put(key, parseValue(json));
        }
        json.endObject();
        return map;
    }

    @NonNull
    private List<Object> parseArray(@NonNull JsonReader json) throws IOException {
        json.beginArray();
        final List<Object> list = new ArrayList<>();
        while (json.hasNext()) { list.add(parseValue(json)); }
        json.endArray();
        return list;
    }

    private Object parseValue(@NonNull JsonReader json) throws IOException {
        JsonReader.Token token = json.peek();
        switch (token) {
            case NULL:
                return json.nextNull();
            case BOOLEAN:
                return json.nextBoolean();
            case NUMBER:
                return json.nextLong();
            case STRING:
                return parseString(json.nextString());
            case BEGIN_ARRAY:
                return parseArray(json);
            case BEGIN_OBJECT:
                return parseMap(json);
            default:
                throw new IllegalArgumentException("Unexpected token: " + token);
        }
    }

    private Object parseString(@NonNull String s) {
        switch (s) {
            case "null":
                return null;
            case "true":
                return true;
            case "false":
                return false;
            default: {
                final String suffix = s.substring(1);
                switch (s.substring(0, 1)) {
                    case "I":
                        return Integer.valueOf(suffix);
                    case "L":
                        return Long.valueOf(suffix);
                    case "F":
                    case "D":
                        return Float.valueOf(suffix);
                    case "\"":
                        return !suffix.endsWith("\"") ? suffix : suffix.substring(0, s.length() - 1);
                    case "@":
                        return new Memory.Ref(suffix);
                    default:
                        return s;
                }
            }
        }
    }

    @SuppressWarnings("PMD.NPathComplexity")
    private void serializeValue(@Nullable Object value, @NonNull JsonWriter writer) throws IOException {
        if ((value == null) || ("null".equals(value))) { writer.nullValue(); }
        if (value instanceof Boolean) { writer.value(((Boolean) value) ? "true" : "false"); }
        if (value instanceof Integer) { writer.value("I" + value); }
        if (value instanceof Long) { writer.value("L" + value); }
        if (value instanceof Float) { writer.value("F" + value); }
        if (value instanceof Double) { writer.value("D" + value); }
        if (value instanceof String) { writer.value("\"" + value + "\""); }
        if (value instanceof Memory.Ref) { writer.value("@" + ((Memory.Ref) value).key); }
        if (value instanceof List) { serializeList((List<?>) value, writer); }
        if (value instanceof Map) { serializeMap((Map<?, ?>) value, writer); }
    }

    private void serializeMap(Map<?, ?> value, @NonNull JsonWriter writer) throws IOException {
        writer.beginObject();
        for (Map.Entry<?, ?> entry: value.entrySet()) {
            final Object key = entry.getKey();
            if (!(key instanceof String)) {
                throw new IllegalArgumentException("Key is not a string in serialize: " + key);
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
}

