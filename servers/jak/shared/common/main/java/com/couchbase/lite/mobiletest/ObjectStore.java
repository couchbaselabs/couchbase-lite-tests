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
package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.Collections;
import java.util.List;
import java.util.Map;

// Read only, relatively type safe object store
public class ObjectStore {
    @NonNull
    private final Map<String, Object> args;

    public ObjectStore(@NonNull Map<String, Object> args) { this.args = Collections.unmodifiableMap(args); }

    public boolean contains(@NonNull String name) { return args.containsKey(name); }

    @Nullable
    public Boolean getBoolean(@NonNull String name) { return get(name, Boolean.class); }

    @Nullable
    public Number getNumber(@NonNull String name) { return get(name, Number.class); }

    @Nullable
    public Integer getInt(@NonNull String name) { return get(name, Integer.class); }

    @Nullable
    public Long getLong(@NonNull String name) { return get(name, Long.class); }

    @Nullable
    public Float getFloat(@NonNull String name) { return get(name, Float.class); }

    @Nullable
    public Double getDouble(@NonNull String name) { return get(name, Double.class); }

    @Nullable
    public String getString(@NonNull String name) { return get(name, String.class); }

    @Nullable
    public byte[] getData(@NonNull String name) { return get(name, byte[].class); }

    @SuppressWarnings("rawtypes")
    @Nullable
    public List getList(@NonNull String name) { return get(name, List.class); }

    @SuppressWarnings("rawtypes")
    @Nullable
    public Map getMap(@NonNull String name) { return get(name, Map.class); }

    @Nullable
    public <T> T get(@NonNull String name, @NonNull Class<T> expectedType) {
        final Object val = args.get(name);
        if (val == null) { return null; }
        final Class<?> actualType = val.getClass();
        if (expectedType.isAssignableFrom(actualType)) { return expectedType.cast(val); }
        throw new IllegalArgumentException("Cannot convert " + actualType + " to " + expectedType);
    }
}
