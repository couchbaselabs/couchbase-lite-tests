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

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.mobiletest.errors.ServerError;


public class TypedList extends TypedCollection {
    @NonNull
    private final List<Object> args;

    public TypedList() { this(new ArrayList<>()); }

    public TypedList(@NonNull List<Object> args) { this(args, true); }

    public TypedList(@NonNull List<Object> args, boolean strict) {
        super(strict);
        this.args = args;
    }

    public final boolean isEmpty() { return args.isEmpty(); }

    public int size() { return args.size(); }

    @Nullable
    public Boolean getBoolean(int pos) { return get(pos, Boolean.class); }

    @Nullable
    public Number getNumber(int pos) { return get(pos, Number.class); }

    @Nullable
    public Integer getInt(int pos) { return get(pos, Integer.class); }

    @Nullable
    public Long getLong(int pos) { return get(pos, Long.class); }

    @Nullable
    public Float getFloat(int pos) { return get(pos, Float.class); }

    @Nullable
    public Double getDouble(int pos) { return get(pos, Double.class); }

    @Nullable
    public String getString(int pos) { return get(pos, String.class); }

    @Nullable
    public byte[] getData(int pos) { return get(pos, byte[].class); }

    @SuppressWarnings("unchecked")
    @Nullable
    public TypedList getList(int pos) {
        final List<Object> val = get(pos, List.class);
        return (val == null) ? null : new TypedList(val);
    }

    @SuppressWarnings("unchecked")
    @Nullable
    public TypedMap getMap(int pos) {
        final Map<String, Object> val = get(pos, Map.class);
        return (val == null) ? null : new TypedMap(val);
    }

    @Nullable
    public <T> T get(int pos, @NonNull Class<T> expectedType) { return checkType(expectedType, args.get(pos)); }

    @Nullable
    public Class<?> getType(int pos) {
        final Object val = args.get(pos);
        return (val == null) ? null : val.getClass();
    }

    public void add(@Nullable Object val) { args.add(val); }

    public static class TreeReduce<T> {
        public interface MapOp<T> {
            @Nullable
            MapOp<T> startMap(@NonNull String key, @NonNull T acc);
            @Nullable
            ListOp<T> startList(@NonNull String key, @NonNull T acc);
            @NonNull
            T strVal(@NonNull String key, @NonNull String str, @NonNull T acc);
            @NonNull
            T doubleVal(@NonNull String key, @NonNull Number num, @NonNull T acc);
            @NonNull
            T floatVal(@NonNull String key, @NonNull Number num, @NonNull T acc);
            @NonNull
            T longVal(@NonNull String key, @NonNull Number num, @NonNull T acc);
            @NonNull
            T intVal(@NonNull String key, @NonNull Number num, @NonNull T acc);
            @NonNull
            T boolVal(@NonNull String key, @NonNull Boolean bool, @NonNull T acc);
            @NonNull
            T nullVal(@NonNull String key, @NonNull T acc);
            @NonNull
            T endMap(@NonNull T acc);
        }

        public interface ListOp<T> {
            @Nullable
            MapOp<T> startMap(int idx, @NonNull T acc);
            @Nullable
            ListOp<T> startList(int idx, @NonNull T acc);
            @NonNull
            T strVal(int idx, @NonNull String str, @NonNull T acc);
            @NonNull
            T doubleVal(int idx, @NonNull Number num, @NonNull T acc);
            @NonNull
            T floatVal(int idx, @NonNull Number num, @NonNull T acc);
            @NonNull
            T longVal(int idx, @NonNull Number num, @NonNull T acc);
            @NonNull
            T intVal(int idx, @NonNull Number num, @NonNull T acc);
            @NonNull
            T boolVal(int idx, @NonNull Boolean bool, @NonNull T acc);
            @NonNull
            T nullVal(int idx, @NonNull T acc);
            @NonNull
            T endList(@NonNull T acc);
        }

        @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
        @SuppressWarnings("ConstantConditions")
        @NonNull
        public T reduce(@NonNull TypedMap map, @NonNull MapOp<T> block, @NonNull T acc) {
            T ret = acc;
            for (String key: map.getKeys()) {
                final Class<?> type = map.getType(key);

                if (type == null) {
                    ret = block.nullVal(key, ret);
                    continue;
                }

                if (Map.class.isAssignableFrom(type)) {
                    final MapOp<T> op = block.startMap(key, ret);
                    if (op != null) { ret = reduce(map.getMap(key), op, ret); }
                    continue;
                }

                if (List.class.isAssignableFrom(type)) {
                    final ListOp<T> op = block.startList(key, ret);
                    if (op != null) { ret = reduce(map.getList(key), op, ret); }
                    continue;
                }

                if (String.class.isAssignableFrom(type)) {
                    ret = block.strVal(key, map.getString(key), ret);
                    continue;
                }

                if (Double.class.isAssignableFrom(type)) {
                    ret = block.doubleVal(key, map.getDouble(key), ret);
                    continue;
                }

                if (Float.class.isAssignableFrom(type)) {
                    ret = block.floatVal(key, map.getFloat(key), ret);
                    continue;
                }

                if (Long.class.isAssignableFrom(type)) {
                    ret = block.longVal(key, map.getLong(key), ret);
                    continue;
                }

                if (Integer.class.isAssignableFrom(type)) {
                    ret = block.intVal(key, map.getInt(key), ret);
                    continue;
                }

                if (Boolean.class.isAssignableFrom(type)) {
                    ret = block.boolVal(key, map.getBoolean(key), ret);
                    continue;
                }

                throw new ServerError("Unrecognized type in map.reduce: " + type.getCanonicalName());
            }

            return block.endMap(ret);
        }

        @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
        @SuppressWarnings("ConstantConditions")
        @NonNull
        public T reduce(@NonNull TypedList list, @NonNull ListOp<T> block, @NonNull T acc)  {
            T ret = acc;
            final int n = list.size();
            for (int idx = 0; idx < n; idx++) {
                final Class<?> type = list.getType(idx);

                if (type == null) {
                    ret = block.nullVal(idx, ret);
                    continue;
                }

                if (Map.class.isAssignableFrom(type)) {
                    final MapOp<T> op = block.startMap(idx, ret);
                    if (op != null) { ret = reduce(list.getMap(idx), op, ret); }
                    continue;
                }

                if (List.class.isAssignableFrom(type)) {
                    final ListOp<T> op = block.startList(idx, ret);
                    if (op != null) { ret = reduce(list.getList(idx), op, ret); }
                    continue;
                }

                if (String.class.isAssignableFrom(type)) {
                    ret = block.strVal(idx, list.getString(idx), ret);
                    continue;
                }

                if (Double.class.isAssignableFrom(type)) {
                    ret = block.doubleVal(idx, list.getDouble(idx), ret);
                    continue;
                }

                if (Float.class.isAssignableFrom(type)) {
                    ret = block.floatVal(idx, list.getFloat(idx), ret);
                    continue;
                }

                if (Long.class.isAssignableFrom(type)) {
                    ret = block.longVal(idx, list.getLong(idx), ret);
                    continue;
                }

                if (Integer.class.isAssignableFrom(type)) {
                    ret = block.intVal(idx, list.getInt(idx), ret);
                    continue;
                }

                if (Boolean.class.isAssignableFrom(type)) {
                    ret = block.boolVal(idx, list.getBoolean(idx), ret);
                    continue;
                }

                throw new ServerError("Unrecognized type in list.reduce: " + type.getCanonicalName());
            }

            return block.endList(ret);
        }
    }
}
