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

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

import org.json.JSONArray;
import org.json.JSONObject;

import com.couchbase.lite.mobiletest.errors.ClientError;


public class CompareJsonArray implements JsonReduce.ArrayOp<Boolean> {
    private final JSONArray target;
    private final List<Boolean> indices;

    public CompareJsonArray(@NonNull JSONArray target) {
        this.target = target;
        this.indices = new ArrayList<>(Collections.nCopies(target.length(), false));
    }

    @Nullable
    @Override
    public JsonReduce.ObjectOp<Boolean> startObject(int idx, @NonNull Boolean acc) {
        indices.set(idx, true);
        final JSONObject obj = target.optJSONObject(idx);
        return (!acc || (obj == null)) ? null : new CompareJsonObject(obj);
    }

    @Nullable
    @Override
    public JsonReduce.ArrayOp<Boolean> startArray(int idx, @NonNull Boolean acc) {
        indices.set(idx, true);
        final JSONArray array = target.optJSONArray(idx);
        return (!acc || (array == null)) ? null : new CompareJsonArray(array);
    }

    @NonNull
    @Override
    public Boolean strVal(int idx, @NonNull String str, @NonNull Boolean acc) {
        indices.set(idx, true);
        return acc && str.equals(target.optString(idx));
    }

    @NonNull
    @Override
    public Boolean numVal(int idx, @NonNull Number num, @NonNull Boolean acc) {
        indices.set(idx, true);
        if (!acc) { return false; }

        if (num instanceof Integer) { return num.equals(target.optInt(idx)); }
        if (num instanceof Long) { return num.equals(target.optLong(idx)); }
        if (num instanceof Double) { return num.equals(target.optDouble(idx)); }

        throw new ClientError("unrecognized Number: ${num::class.java.name}");
    }

    @NonNull
    @Override
    public Boolean boolVal(int idx, @NonNull Boolean bool, @NonNull Boolean acc) {
        indices.set(idx, true);
        return acc && bool.equals(target.optBoolean(idx));
    }

    @NonNull
    @Override
    public Boolean nullVal(int idx, @NonNull Boolean acc) {
        indices.set(idx, true);
        return acc && target.isNull(idx);
    }

    @NonNull
    @Override
    public Boolean endArray(@NonNull Boolean acc) { return acc && !indices.contains(Boolean.FALSE); }
}
