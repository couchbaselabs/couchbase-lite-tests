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
package com.couchbase.lite.mobiletest.trees;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.List;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.mobiletest.errors.ServerError;


/**
 * Me: Can you name any of the patterns they covered?
 * Them: I loved the Singleton pattern!
 * Me: OK. Were there any others?
 * Them: Uh, I think there was one called the Visitater.
 * Me: Oooh, that's right! The one that visits potatoes. I use it all the time. Next!!!
 */
@SuppressWarnings("PMD.NPathComplexity")
public class TreeEach {
    public interface MapOp {
        @Nullable
        MapOp startMap(@NonNull String key);
        @Nullable
        ListOp startList(@NonNull String key);
        void strVal(@NonNull String key, @NonNull String str);
        void numVal(@NonNull String key, @NonNull Double num);
        void numVal(@NonNull String key, @NonNull Float num);
        void numVal(@NonNull String key, @NonNull Long num);
        void numVal(@NonNull String key, @NonNull Integer num);
        void boolVal(@NonNull String key, @NonNull Boolean bool);
        void nullVal(@NonNull String key);
        void endMap();
    }

    public interface ListOp {
        @Nullable
        MapOp startMap(int idx);
        @Nullable
        ListOp startList(int idx);
        void strVal(int idx, @NonNull String str);
        void numVal(int idx, @NonNull Double num);
        void numVal(int idx, @NonNull Float num);
        void numVal(int idx, @NonNull Long num);
        void numVal(int idx, @NonNull Integer num);
        void boolVal(int idx, @NonNull Boolean bool);
        void nullVal(int idx);
        void endList();
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @SuppressWarnings("ConstantConditions")
    public void forEach(@NonNull TypedMap map, @NonNull MapOp block) {
        for (String key: map.getKeys()) {
            final Class<?> type = map.getType(key);

            if (type == null) {
                block.nullVal(key);
                continue;
            }

            if (Map.class.isAssignableFrom(type)) {
                final MapOp op = block.startMap(key);
                if (op != null) { forEach(map.getMap(key), op); }
                continue;
            }

            if (List.class.isAssignableFrom(type)) {
                final ListOp op = block.startList(key);
                if (op != null) { forEach(map.getList(key), op); }
                continue;
            }

            if (String.class.isAssignableFrom(type)) {
                block.strVal(key, map.getString(key));
                continue;
            }

            if (Double.class.isAssignableFrom(type)) {
                block.numVal(key, map.getDouble(key));
                continue;
            }

            if (Float.class.isAssignableFrom(type)) {
                block.numVal(key, map.getFloat(key));
                continue;
            }

            if (Long.class.isAssignableFrom(type)) {
                block.numVal(key, map.getLong(key));
                continue;
            }

            if (Integer.class.isAssignableFrom(type)) {
                block.numVal(key, map.getInt(key));
                continue;
            }

            if (Boolean.class.isAssignableFrom(type)) {
                block.boolVal(key, map.getBoolean(key));
                continue;
            }

            throw new ServerError("Unrecognized type in map.each: " + type.getCanonicalName());
        }

        block.endMap();
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @SuppressWarnings("ConstantConditions")
    public void forEach(@NonNull TypedList list, @NonNull ListOp block) {
        final int n = list.size();
        for (int idx = 0; idx < n; idx++) {
            final Class<?> type = list.getType(idx);

            if (type == null) {
                block.nullVal(idx);
                continue;
            }

            if (Map.class.isAssignableFrom(type)) {
                final MapOp op = block.startMap(idx);
                if (op != null) { forEach(list.getMap(idx), op); }
                continue;
            }

            if (List.class.isAssignableFrom(type)) {
                final ListOp op = block.startList(idx);
                if (op != null) { forEach(list.getList(idx), op); }
                continue;
            }

            if (String.class.isAssignableFrom(type)) {
                block.strVal(idx, list.getString(idx));
                continue;
            }

            if (Double.class.isAssignableFrom(type)) {
                block.numVal(idx, list.getDouble(idx));
                continue;
            }

            if (Float.class.isAssignableFrom(type)) {
                block.numVal(idx, list.getFloat(idx));
                continue;
            }

            if (Long.class.isAssignableFrom(type)) {
                block.numVal(idx, list.getLong(idx));
                continue;
            }

            if (Integer.class.isAssignableFrom(type)) {
                block.numVal(idx, list.getInt(idx));
                continue;
            }

            if (Boolean.class.isAssignableFrom(type)) {
                block.boolVal(idx, list.getBoolean(idx));
                continue;
            }

            throw new ServerError("Unrecognized type in list.each: " + type.getCanonicalName());
        }

        block.endList();
    }
}

