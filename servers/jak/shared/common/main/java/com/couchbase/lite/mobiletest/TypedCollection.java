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


abstract class TypedCollection {
    private final boolean strict;

    TypedCollection(boolean strict) { this.strict = strict; }

    @Nullable
    protected final <T> T getT(@NonNull Class<T> expectedType, @Nullable Object val) {
        if (val == null) { return null; }
        final Class<?> actualType = val.getClass();
        if (expectedType.isAssignableFrom(actualType)) { return expectedType.cast(val); }
        if (!strict) { return null; }
        throw new TestException(TestException.TESTSERVER, 0, "Cannot convert " + actualType + " to " + expectedType);
    }
}
