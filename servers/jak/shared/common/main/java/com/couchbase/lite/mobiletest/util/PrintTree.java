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
package com.couchbase.lite.mobiletest.util;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TreeEach;


public class PrintTree implements TreeEach.MapOp, TreeEach.ListOp {
    private static final String TAG = "REQ";


    private final String tag;

    public PrintTree(@NonNull String tag) { this.tag = tag; }

    @Nullable
    @Override
    public TreeEach.MapOp startMap(@NonNull String key) {
        Log.p(TAG, "start map @" + key);
        return new PrintTree(key);
    }

    @Nullable
    @Override
    public TreeEach.MapOp startMap(int idx) {
        Log.p(TAG, "start map @" + idx);
        return new PrintTree(String.valueOf(idx));
    }

    @Override
    public void endMap() {
        Log.p(TAG, "end object @" + tag);
    }

    @Nullable
    @Override
    public TreeEach.ListOp startList(@NonNull String key) {
        Log.p(TAG, "start list @" + key);
        return new PrintTree(key);
    }

    @Nullable
    @Override
    public TreeEach.ListOp startList(int idx) {
        Log.p(TAG, "start list @" + idx);
        return new PrintTree(String.valueOf(idx));
    }

    @Override
    public void endList() {
        Log.p(TAG, "end list @" + tag);
    }

    @Override
    public void strVal(@NonNull String key, @NonNull String str) {
        Log.p(TAG, "string @" + key + ": " + str);
    }

    @Override
    public void strVal(int idx, @NonNull String str) {
        Log.p(TAG, "string @" + idx + ": " + str);
    }

    @Override
    public void numVal(@NonNull String key, @NonNull Double num) {
        Log.p(TAG, "double @" + key + ": " + num);
    }

    @Override
    public void numVal(int idx, @NonNull Double num) {
        Log.p(TAG, "double @" + idx + ": " + num);
    }

    @Override
    public void numVal(@NonNull String key, @NonNull Float num) {
        Log.p(TAG, "float @" + key + ": " + num);
    }

    @Override
    public void numVal(int idx, @NonNull Float num) {
        Log.p(TAG, "float @" + idx + ": " + num);
    }

    @Override
    public void numVal(@NonNull String key, @NonNull Long num) {
        Log.p(TAG, "long @" + key + ": " + num);
    }

    @Override
    public void numVal(int idx, @NonNull Long num) {
        Log.p(TAG, "long @" + idx + ": " + num);
    }

    @Override
    public void numVal(@NonNull String key, @NonNull Integer num) {
        Log.p(TAG, "integer @" + key + ": " + num);
    }

    @Override
    public void numVal(int idx, @NonNull Integer num) {
        Log.p(TAG, "integer @" + idx + ": " + num);
    }

    @Override
    public void boolVal(@NonNull String key, @NonNull Boolean bool) {
        Log.p(TAG, "bool @" + key + ": " + bool);
    }

    @Override
    public void boolVal(int idx, @NonNull Boolean bool) {
        Log.p(TAG, "bool @" + idx + ": " + bool);
    }

    @Override
    public void nullVal(@NonNull String key) {
        Log.p(TAG, "null @" + key);
    }

    @Override
    public void nullVal(int idx) {
        Log.p(TAG, "null @" + idx);
    }
}

