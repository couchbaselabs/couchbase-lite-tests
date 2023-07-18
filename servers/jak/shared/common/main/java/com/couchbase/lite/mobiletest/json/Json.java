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
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import com.squareup.moshi.JsonReader;
import com.squareup.moshi.JsonWriter;
import okio.Buffer;

import com.couchbase.lite.mobiletest.util.Fn;
import com.couchbase.lite.mobiletest.util.Log;


public abstract class Json {
    private static final String TAG = "JSON";

    private static final AtomicInteger PROTOCOL_VERSION = new AtomicInteger(-1);

    private static final List<Fn.Supplier<Json>> PROTOCOLS;
    static {
        final List<Fn.Supplier<Json>> l = new ArrayList<>();
        l.add(JsonV0::new);
        l.add(JsonV1::new);
        PROTOCOLS = Collections.unmodifiableList(l);
    }
    @NonNull
    public static Json getParser(int version) {
        checkVersion(version);

        final Fn.Supplier<Json> supplier = ((version < 0) || (version > (PROTOCOLS.size() - 1)))
            ? null
            : PROTOCOLS.get(version);

        if (supplier == null) {
            throw new IllegalArgumentException("Unsupported protocol version: " + version);
        }

        return supplier.get();
    }

    @NonNull
    public static Json getSerializer(int version) {
        checkVersion(version);

        if (version > (PROTOCOLS.size() - 1)) {
            throw new IllegalArgumentException("Unsupported protocol version: " + version);
        }

        return PROTOCOLS.get(version).get();
    }


    @NonNull
    public abstract Map<String, Object> parseRequest(@NonNull InputStream json) throws IOException;

    @NonNull
    public abstract Buffer serializeReply(@Nullable Map<String, Object> reply) throws IOException;

    @Nullable
    protected abstract Object parseString(@NonNull String s);

    protected abstract void serializeValue(@Nullable Object value, @NonNull JsonWriter writer) throws IOException;

    @NonNull
    protected final Map<String, Object> parseMap(@NonNull JsonReader json) throws IOException {
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
    protected final List<Object> parseArray(@NonNull JsonReader json) throws IOException {
        json.beginArray();
        final List<Object> list = new ArrayList<>();
        while (json.hasNext()) { list.add(parseValue(json)); }
        json.endArray();
        return list;
    }

    protected final void serializeMap(Map<?, ?> value, @NonNull JsonWriter writer) throws IOException {
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

    protected final void serializeList(List<?> value, @NonNull JsonWriter writer) throws IOException {
        writer.beginArray();
        for (Object item: value) { serializeValue(item, writer); }
        writer.endArray();
    }

    @Nullable
    protected final Object parseValue(@NonNull JsonReader json) throws IOException {
        final JsonReader.Token token = json.peek();
        switch (token) {
            case NULL:
                return json.nextNull();
            case BOOLEAN:
                return json.nextBoolean();
            case NUMBER:
                final String s = json.nextString();
                if (s.contains(".")) { return Double.valueOf(s); }
                return Long.valueOf(s);
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

    private static void checkVersion(int version) {
        final int previousVersion = PROTOCOL_VERSION.getAndSet(version);
        if ((previousVersion >= 0) && (version != previousVersion)) {
            Log.w(TAG, "Request protocol changed for parser: " + previousVersion + " => " + version);
        }
    }
}
