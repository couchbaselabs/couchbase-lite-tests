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


public class UpdateJsonArray implements JsonEach.ArrayOp {
    private final JSONArray target;

    public UpdateJsonArray(@NonNull JSONArray target) { this.target = target; }

    @NonNull
    @Override
    public JsonEach.ObjectOp startObject(int idx) {
        JSONObject obj = target.optJSONObject(idx);
        if (obj == null) {
            obj = new JSONObject();
            updateTarget(idx, obj);
        }
        return new UpdateJsonObject(obj);
    }

    @NonNull
    @Override
    public JsonEach.ArrayOp startArray(int idx) {
        JSONArray array = target.optJSONArray(idx);
        if (array == null) {
            array = new JSONArray();
            updateTarget(idx, array);
        }

        return new UpdateJsonArray(array);
    }

    @Override
    public void strVal(int idx, @NonNull String str) {
        if (!str.equals(target.optString(idx))) { updateTarget(idx, str); }
    }

    @Override
    public void numVal(int idx, @NonNull Number num) {
        final boolean needsUpdate;
        if (num instanceof Integer) { needsUpdate = num.equals(target.optInt(idx)); }
        else if (num instanceof Long) { needsUpdate = num.equals(target.optLong(idx)); }
        else if (num instanceof Double) { needsUpdate = num.equals(target.optDouble(idx)); }
        else { throw new ClientError("unrecognized Number: " + num.getClass().getName()); }
        if (needsUpdate) { updateTarget(idx, num); }
    }

    @Override
    public void boolVal(int idx, @NonNull Boolean bool) {
        if (bool != target.optBoolean(idx)) { updateTarget(idx, bool); }
    }

    @Override
    public void nullVal(int idx) {
        if (!target.isNull(idx)) { updateTarget(idx, JSONObject.NULL); }
    }

    @Override
    public void endArray() { }

    private void updateTarget(int idx, Object value) {
        try { target.put(idx, value); }
        catch (JSONException e) { throw new ServerError("Failed updating JSON at index: " + idx, e); }
    }
}
