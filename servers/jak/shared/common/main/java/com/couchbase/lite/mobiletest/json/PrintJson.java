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

import com.couchbase.lite.mobiletest.util.Log;


public class PrintJson implements JsonEach.ObjectOp, JsonEach.ArrayOp {
    private static final String TAG = "JPRINT";


    private final String tag;

    public PrintJson(@NonNull String tag) { this.tag = tag; }

    @Nullable
    @Override
    public JsonEach.ObjectOp startObject(@NonNull String key) {
        Log.d(TAG, "start object @" + key);
        return new PrintJson(key);
    }

    @Nullable
    @Override
    public JsonEach.ObjectOp startObject(int idx) {
        Log.d(TAG, "start object @" + idx);
        return new PrintJson(String.valueOf(idx));
    }

    @Override
    public void endObject() {
        Log.d(TAG, "end object @" + tag);
    }

    @Nullable
    @Override
    public JsonEach.ArrayOp startArray(@NonNull String key) {
        Log.d(TAG, "start array @" + key);
        return new PrintJson(key);
    }

    @Nullable
    @Override
    public JsonEach.ArrayOp startArray(int idx) {
        Log.d(TAG, "start array @" + idx);
        return new PrintJson(String.valueOf(idx));
    }

    @Override
    public void endArray() {
        Log.d(TAG, "end array @" + tag);
    }

    @Override
    public void strVal(@NonNull String key, @NonNull String str) {
        Log.d(TAG, "string @" + key + ": " + str);
    }

    @Override
    public void strVal(int idx, @NonNull String str) {
        Log.d(TAG, "string @" + idx + ": " + str);
    }

    @Override
    public void numVal(@NonNull String key, @NonNull Number num) {
        Log.d(TAG, "number @" + key + ": " + num);
    }

    @Override
    public void numVal(int idx, @NonNull Number num) {
        Log.d(TAG, "number @" + idx + ": " + num);
    }

    @Override
    public void boolVal(@NonNull String key, @NonNull Boolean bool) {
        Log.d(TAG, "bool @" + key + ": " + bool);
    }

    @Override
    public void boolVal(int idx, @NonNull Boolean bool) {
        Log.d(TAG, "bool @" + idx + ": " + bool);
    }

    @Override
    public void nullVal(@NonNull String key) {
        Log.d(TAG, "null @" + key);
    }

    @Override
    public void nullVal(int idx) {
        Log.d(TAG, "null @" + idx);
    }
}

