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
package com.couchbase.lite.mobiletest.orts;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import org.json.JSONArray;
import org.json.JSONObject;

import com.couchbase.lite.mobiletest.errors.ClientError;


public class CompareJsonObject implements JsonReduce.ObjectOp<Boolean> {
    private final JSONObject target;
    private final List<String> keys = new ArrayList<>();

    @SuppressWarnings({"PMD.ForLoopCanBeForeach", "EmptyForIteratorPad"})
    public CompareJsonObject(@NonNull JSONObject target) {
        this.target = target;

        // Android JSONObject doesn't have a getKeys()
        for (Iterator<String> keyItr = target.keys(); keyItr.hasNext(); ) { keys.add(keyItr.next()); }
    }

    @Nullable
    @Override
    public JsonReduce.ObjectOp<Boolean> startObject(@NonNull String key, @NonNull Boolean acc) {
        keys.remove(key);
        final JSONObject obj = target.optJSONObject(key);
        return (!acc || (obj == null)) ? null : new CompareJsonObject(obj);
    }

    @Nullable
    @Override
    public JsonReduce.ArrayOp<Boolean> startArray(@NonNull String key, @NonNull Boolean acc) {
        keys.remove(key);
        final JSONArray array = target.optJSONArray(key);
        return (!acc || (array == null)) ? null : new CompareJsonArray(array);
    }

    @NonNull
    @Override
    public Boolean strVal(@NonNull String key, @NonNull String str, @NonNull Boolean acc) {
        keys.remove(key);
        return acc && str.equals(target.optString(key));
    }

    @NonNull
    @Override
    public Boolean numVal(@NonNull String key, @NonNull Number num, @NonNull Boolean acc) {
        keys.remove(key);
        if (!acc) { return false; }

        if (num instanceof Integer) { return num.equals(target.optInt(key)); }
        if (num instanceof Long) { return num.equals(target.optLong(key)); }
        if (num instanceof Double) { return num.equals(target.optDouble(key)); }

        throw new ClientError("unrecognized Number: ${num::class.java.name}");
    }

    @NonNull
    @Override
    public Boolean boolVal(@NonNull String key, @NonNull Boolean bool, @NonNull Boolean acc) {
        keys.remove(key);
        return acc && bool.equals(target.optBoolean(key));
    }

    @NonNull
    @Override
    public Boolean nullVal(@NonNull String key, @NonNull Boolean acc) {
        keys.remove(key);
        return acc && target.isNull(key);
    }

    @NonNull
    @Override
    public Boolean endObject(@NonNull Boolean acc) { return acc && keys.isEmpty(); }
}

