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

import java.util.Iterator;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;


public class JsonReduce<T> {

    public interface ObjectOp<T> {
        @Nullable
        ObjectOp<T> startObject(@NonNull String key, @NonNull T acc);
        @Nullable
        ArrayOp<T> startArray(@NonNull String key, @NonNull T acc);
        @NonNull
        T strVal(@NonNull String key, @NonNull String str, @NonNull T acc);
        @NonNull
        T numVal(@NonNull String key, @NonNull Number num, @NonNull T acc);
        @NonNull
        T boolVal(@NonNull String key, @NonNull Boolean bool, @NonNull T acc);
        @NonNull
        T nullVal(@NonNull String key, @NonNull T acc);
        @NonNull
        T endObject(@NonNull T acc);
    }

    public interface ArrayOp<T> {
        @Nullable
        ObjectOp<T> startObject(int idx, @NonNull T acc);
        @Nullable
        ArrayOp<T> startArray(int idx, @NonNull T acc);
        @NonNull
        T strVal(int idx, @NonNull String str, @NonNull T acc);
        @NonNull
        T numVal(int idx, @NonNull Number num, @NonNull T acc);
        @NonNull
        T boolVal(int idx, @NonNull Boolean bool, @NonNull T acc);
        @NonNull
        T nullVal(int idx, @NonNull T acc);
        @NonNull
        T endArray(@NonNull T acc);
    }

    @SuppressWarnings({"PMD.ForLoopCanBeForeach", "EmptyForIteratorPad"})
    @NonNull
    public T reduce(@NonNull JSONObject obj, @NonNull ObjectOp<T> block, @NonNull T acc) throws JSONException {
        T ret = acc;
        // Android JSONObject doesn't have a getKeys()
        for (Iterator<String> keyItr = obj.keys(); keyItr.hasNext(); ) {
            final String key = keyItr.next();
            final Object value = obj.get(key);

            if (value instanceof JSONObject) {
                final ObjectOp<T> jobj = block.startObject(key, ret);
                if (jobj != null) { ret = reduce(((JSONObject) value), jobj, ret); }
                continue;
            }

            if (value instanceof JSONArray) {
                final ArrayOp<T> jarr = block.startArray(key, ret);
                if (jarr != null) { ret = reduce(((JSONArray) value), jarr, ret); }
                continue;
            }

            if (value instanceof String) {
                ret = block.strVal(key, ((String) value), ret);
                continue;
            }

            if (value instanceof Number) {
                ret = block.numVal(key, ((Number) value), ret);
                continue;
            }

            if (value instanceof Boolean) {
                ret = block.boolVal(key, ((Boolean) value), ret);
                continue;
            }

            if (value == JSONObject.NULL) {
                ret = block.nullVal(key, ret);
                continue;
            }

            throw new IllegalArgumentException("unrecognized JSON type: ${value::class.java.name}");
        }

        return block.endObject(ret);
    }

    @NonNull
    public T reduce(@NonNull JSONArray obj, @NonNull ArrayOp<T> block, @NonNull T acc) throws JSONException {
        T ret = acc;
        for (int idx = 0; idx < obj.length(); idx++) {
            final Object value = obj.get(idx);

            if (value instanceof JSONObject) {
                final ObjectOp<T> jobj = block.startObject(idx, ret);
                if (jobj != null) { ret = reduce(((JSONObject) value), jobj, ret); }
                continue;
            }

            if (value instanceof JSONArray) {
                final ArrayOp<T> jarr = block.startArray(idx, ret);
                if (jarr != null) { ret = reduce(((JSONArray) value), jarr, ret); }
                continue;
            }

            if (value instanceof String) {
                ret = block.strVal(idx, ((String) value), ret);
                continue;
            }

            if (value instanceof Number) {
                ret = block.numVal(idx, ((Number) value), ret);
                continue;
            }

            if (value instanceof Boolean) {
                ret = block.boolVal(idx, ((Boolean) value), ret);
                continue;
            }

            if (value == JSONObject.NULL) {
                ret = block.nullVal(idx, ret);
                continue;
            }

            throw new IllegalArgumentException("unrecognized JSON type: ${value::class.java.name}");
        }
        return block.endArray(ret);
    }
}

