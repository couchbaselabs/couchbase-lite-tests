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
import java.util.HashMap;
import java.util.List;
import java.util.Map;


// Read only, relatively type safe object store
// Not thread safe...
public class TypedMap extends TypedCollection {
    @NonNull
    private final Map<String, Object> args;

    public TypedMap(@Nullable Map<?, ?> args) { this(args, true); }

    @SuppressWarnings("unchecked")
    public TypedMap(@Nullable Map<?, ?> args, boolean strict) {
        super(strict);
        this.args = Collections.unmodifiableMap((args != null) ? (Map<String, Object>) args : new HashMap<>());
    }

    public boolean contains(@NonNull String key) { return args.containsKey(key); }

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
    public List<Object> getList(@NonNull String key) { return get(key, List.class); }

    @SuppressWarnings("unchecked")
    @Nullable
    public Map<String, Object> getMap(@NonNull String key) { return get(key, Map.class); }

    @Nullable
    protected <T> T get(@NonNull String key, @NonNull Class<T> expectedType) {
        return getT(expectedType, args.get(key));
    }
}
