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
package com.couchbase.lite.mobiletest.factories;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.squareup.moshi.JsonReader;
import okio.Okio;

import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.ClientError;


public class RequestBuilder {
    private final InputStream json;

    public RequestBuilder(@NonNull InputStream json) { this.json = json; }

    @NonNull
    public TypedMap buildRequest() throws IOException {
        final JsonReader reader = JsonReader.of(Okio.buffer(Okio.source(json)));
        reader.setLenient(true);
        // ??? should check for extraneous stuff at the end of the document, wo hanging
        return new TypedMap(parseMap(reader));
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

    @Nullable
    private Object parseValue(@NonNull JsonReader json) throws IOException {
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
                return json.nextString();
            case BEGIN_ARRAY:
                return parseArray(json);
            case BEGIN_OBJECT:
                return parseMap(json);
            default:
                throw new ClientError("Unexpected token: " + token);
        }
    }
}
