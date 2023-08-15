//
// Copyright (c) 2022 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.mobiletest.data;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.Collection;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.errors.ClientError;


// Read only, relatively type safe object store
// Not thread safe...
public class TypedMap extends TypedCollection {
    @NonNull
    private final Map<String, Object> data;

    public TypedMap() { this(new HashMap<>()); }

    public TypedMap(@NonNull Map<?, ?> data) { this(data, true); }

    @SuppressWarnings("unchecked")
    public TypedMap(@NonNull Map<?, ?> data, boolean strict) {
        super(strict);
        this.data = (Map<String, Object>) data;
    }

    public void validate(Collection<String> expected) {
        final Set<String> keys = getKeys();
        keys.removeAll(expected);
        if (!keys.isEmpty()) { throw new ClientError("Unexpected keys: " + String.join(",", keys)); }
    }

    @NonNull
    public Set<String> getKeys() { return new HashSet<>(data.keySet()); }

    @Nullable
    public Boolean getBoolean(@NonNull String key) { return get(key, Boolean.class); }

    @Nullable
    public Number getNumber(@NonNull String key) { return get(key, Number.class); }

    @Nullable
    public Integer getInt(@NonNull String key) { return get(key, Integer.class); }

    @Nullable
    public Long getLong(@NonNull String key) { return get(key, Long.class); }

    @Nullable
    public Float getFloat(@NonNull String key) { return get(key, Float.class); }

    @Nullable
    public Double getDouble(@NonNull String key) { return get(key, Double.class); }

    @Nullable
    public String getString(@NonNull String key) { return get(key, String.class); }

    @Nullable
    public byte[] getData(@NonNull String key) { return get(key, byte[].class); }

    @SuppressWarnings("unchecked")
    @Nullable
    public TypedList getList(@NonNull String key) {
        final List<Object> val = get(key, List.class);
        return (val == null) ? null : new TypedList(val);
    }

    @SuppressWarnings("unchecked")
    @Nullable
    public TypedMap getMap(@NonNull String key) {
        final Map<String, Object> val = get(key, Map.class);
        return (val == null) ? null : new TypedMap(val);
    }

    // Bypass the whole typing mechanism
    @Nullable
    public Object getObject(@NonNull String key) { return data.get(key); }

    @Nullable
    public <T> T get(@NonNull String key, @NonNull Class<T> expectedType) {
        return checkType(expectedType, data.get(key));
    }

    @Nullable
    public Class<?> getType(@NonNull String key) {
        final Object val = data.get(key);
        return (val == null) ? null : val.getClass();
    }

    public void put(@NonNull String key, @Nullable Object val) { data.put(key, val); }
}
