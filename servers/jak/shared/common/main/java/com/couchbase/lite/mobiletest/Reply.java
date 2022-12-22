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

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.squareup.moshi.Moshi;


public final class Reply {
    public static final Reply EMPTY = create("I-1");

    private static final Moshi SERIALIZER = new Moshi.Builder().build();

    @NonNull
    public static Reply create(@NonNull String type, @NonNull byte[] data) { return new Reply(type, data); }

    @NonNull
    public static Reply create(@NonNull String str) { return new Reply("text/plain", '"' + str + '"'); }

    @NonNull
    public static Reply create(@NonNull Object data, @NonNull Memory mem) {
        return new Reply("text/plain", serialize(data, mem));
    }

    @SuppressWarnings("PMD.NPathComplexity")
    @NonNull
    private static String serialize(@Nullable Object value, @NonNull Memory memory) {
        if (value == null) { return "null"; }
        if (value instanceof Boolean) { return ((Boolean) value) ? "true" : "false"; }
        if (value instanceof Integer) { return "I" + value; }
        if (value instanceof Long) { return "L" + value; }
        if (value instanceof Float) { return "F" + value; }
        if (value instanceof Double) { return "D" + value; }
        if (value instanceof String) { return "\"" + value + "\""; }
        if (value instanceof List) {
            final List<String> list = new ArrayList<>();
            for (Object object: (List<?>) value) { list.add(serialize(object, memory)); }
            return SERIALIZER.adapter(List.class).serializeNulls().toJson(list);
        }
        if (value instanceof Map) {
            final Map<String, String> map = new HashMap<>();
            for (Map.Entry<?, ?> entry: ((Map<?, ?>) value).entrySet()) {
                final Object key = entry.getKey();
                if (!(key instanceof String)) {
                    throw new IllegalArgumentException("Key is not a string in serialize: " + key);
                }
                map.put((String) key, serialize(entry.getValue(), memory));
            }
            return SERIALIZER.adapter(Map.class).serializeNulls().toJson(map);
        }

        return memory.add(value);
    }


    private final String contentType;
    private final byte[] data;

    private Reply(@NonNull String contentType, @NonNull String data) {
        this(contentType, data.getBytes(StandardCharsets.UTF_8));
    }

    private Reply(@NonNull String contentType, @NonNull byte[] data) {
        this.contentType = contentType;
        this.data = Arrays.copyOf(data, data.length);
    }

    @NonNull
    public String getContentType() { return contentType; }

    @NonNull
    public byte[] getData() { return Arrays.copyOf(this.data, this.data.length); }
}
