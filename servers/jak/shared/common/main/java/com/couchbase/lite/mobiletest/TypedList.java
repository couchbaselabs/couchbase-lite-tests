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
package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;


public class TypedList extends TypedCollection {
    @NonNull
    private final List<Object> args;

    public TypedList(@Nullable List<Object> args) { this(args, true); }

    public TypedList(@Nullable List<Object> args, boolean strict) {
        super(strict);
        this.args = Collections.unmodifiableList((args != null) ? args : new ArrayList<>());
    }

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
    public List<Object> getList(int pos) { return get(pos, List.class); }

    @SuppressWarnings("unchecked")
    @Nullable
    public Map<String, Object> getMap(int pos) { return get(pos, Map.class); }

    @Nullable
    protected <T> T get(int pos, @NonNull Class<T> expectedType) { return getT(expectedType,  args.get(pos)); }
}
