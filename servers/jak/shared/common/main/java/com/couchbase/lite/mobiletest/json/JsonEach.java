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


public class JsonEach {
    public interface ObjectOp {
        @Nullable
        ObjectOp startObject(@NonNull String key);
        @Nullable
        ArrayOp startArray(@NonNull String key);
        void strVal(@NonNull String key, @NonNull String str);
        void numVal(@NonNull String key, @NonNull Number num);
        void boolVal(@NonNull String key, @NonNull Boolean bool);
        void nullVal(@NonNull String key);
        void endObject();
    }

    public interface ArrayOp {
        @Nullable
        ObjectOp startObject(int idx);
        @Nullable
        ArrayOp startArray(int idx);
        void strVal(int idx, @NonNull String str);
        void numVal(int idx, @NonNull Number num);
        void boolVal(int idx, @NonNull Boolean bool);
        void nullVal(int idx);
        void endArray();
    }

    @SuppressWarnings({"PMD.ForLoopCanBeForeach", "EmptyForIteratorPad"})
    public void forEach(@NonNull JSONObject obj, @NonNull ObjectOp block) throws JSONException {
        // Android JSONObject doesn't have a getKeys()
        for (Iterator<String> keyItr = obj.keys(); keyItr.hasNext(); ) {
            final String key = keyItr.next();
            final Object value = obj.get(key);

            if (value instanceof JSONObject) {
                final ObjectOp jobj = block.startObject(key);
                if (jobj != null) { forEach(((JSONObject) value), jobj); }
                continue;
            }

            if (value instanceof JSONArray) {
                final ArrayOp jarr = block.startArray(key);
                if (jarr != null) { forEach(((JSONArray) value), jarr); }
                continue;
            }

            if (value instanceof String) {
                block.strVal(key, ((String) value));
                continue;
            }

            if (value instanceof Number) {
                block.numVal(key, ((Number) value));
                continue;
            }

            if (value instanceof Boolean) {
                block.boolVal(key, ((Boolean) value));
                continue;
            }

            if (value == JSONObject.NULL) {
                block.nullVal(key);
                continue;
            }

            throw new IllegalArgumentException("unrecognized JSON type: ${value::class.java.name}");
        }

        block.endObject();
    }

    public void forEach(@NonNull JSONArray array, @NonNull ArrayOp block) throws JSONException {
        final int n = array.length();
        for (int idx = 0; idx < n; idx++) {
            final Object elem = array.get(idx);

            if (elem instanceof JSONObject) {
                final ObjectOp jobj = block.startObject(idx);
                if (jobj != null) { forEach(((JSONObject) elem), jobj); }
                continue;
            }

            if (elem instanceof JSONArray) {
                final ArrayOp jarr = block.startArray(idx);
                if (jarr != null) { forEach(((JSONArray) elem), jarr); }
                continue;
            }

            if (elem instanceof String) {
                block.strVal(idx, ((String) elem));
                continue;
            }

            if (elem instanceof Number) {
                block.numVal(idx, ((Number) elem));
                continue;
            }

            if (elem instanceof Boolean) {
                block.boolVal(idx, ((Boolean) elem));
                continue;
            }

            if (elem == JSONObject.NULL) {
                block.nullVal(idx);
                continue;
            }

            throw new IllegalArgumentException("unrecognized JSON type: ${value::class.java.name}");
        }

        block.endArray();
    }
}

