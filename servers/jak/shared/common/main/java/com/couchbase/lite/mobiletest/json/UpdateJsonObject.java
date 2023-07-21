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

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;


public class UpdateJsonObject implements JsonEach.ObjectOp {
    private final JSONObject target;

    public UpdateJsonObject(@NonNull JSONObject target) { this.target = target; }

    @NonNull
    @Override
    public JsonEach.ObjectOp startObject(@NonNull String key) {
        JSONObject obj = target.optJSONObject(key);
        if (obj == null) {
            obj = new JSONObject();
            updateTarget(key, obj);
        }

        return new UpdateJsonObject(obj);
    }

    @NonNull
    @Override
    public JsonEach.ArrayOp startArray(@NonNull String key) {
        JSONArray array = target.optJSONArray(key);
        if (array == null) {
            array = new JSONArray();
            updateTarget(key, array);
        }

        return new UpdateJsonArray(array);
    }

    @Override
    public void strVal(@NonNull String key, @NonNull String str) {
        if (!str.equals(target.optString(key))) { updateTarget(key, str); }
    }

    @Override
    public void numVal(@NonNull String key, @NonNull Number num) {
        final boolean needsUpdate;
        if (num instanceof Integer) { needsUpdate = num.equals(target.optInt(key)); }
        else if (num instanceof Long) { needsUpdate = num.equals(target.optLong(key)); }
        else if (num instanceof Double) { needsUpdate = num.equals(target.optDouble(key)); }
        else { throw new ClientError("unrecognized Number: " + num.getClass().getName()); }
        if (needsUpdate) { updateTarget(key, num); }
    }

    @Override
    public void boolVal(@NonNull String key, @NonNull Boolean bool) {
        if (bool != target.optBoolean(key)) { updateTarget(key, bool); }
    }

    @Override
    public void nullVal(@NonNull String key) {
        if (!target.isNull(key)) { updateTarget(key, JSONObject.NULL); }
    }

    @Override
    public void endObject() { }

    private void updateTarget(@NonNull String key, Object value) {
        try { target.put(key, value); }
        catch (JSONException e) { throw new ServerError("Failed updating JSON at key: " + key, e); }
    }
}

