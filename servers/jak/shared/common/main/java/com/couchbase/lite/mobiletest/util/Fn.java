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

import java.util.ArrayList;
import java.util.Collection;
import java.util.List;


public final class Fn {
    private Fn() {}

    @FunctionalInterface
    public interface Supplier<R> {
        @NonNull
        R get();
    }

    @FunctionalInterface
    interface Function<T, R> {
        @Nullable
        R apply(@NonNull T x);
    }

    @NonNull
    public static <T, R> List<R> mapToList(@NonNull Collection<? extends T> l, @NonNull Function<T, R> fn) {
        final List<R> r = new ArrayList<>(l.size());
        for (T e: l) { r.add(fn.apply(e)); }
        return r;
    }
}
