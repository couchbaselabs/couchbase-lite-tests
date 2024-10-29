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
package com.couchbase.lite.mobiletest.errors;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.CBLError;
import com.couchbase.lite.CouchbaseLiteException;


// Use this to report a Couchbase API failure (CouchbaseLiteException)
public class CblApiFailure extends TestError {
    private static final Map<String, String> DOMAINS;
    static {
        final Map<String, String> m = new HashMap<>();
        m.put(CBLError.Domain.CBLITE, "CBL");
        m.put(CBLError.Domain.POSIX, "POSIX");
        m.put(CBLError.Domain.SQLITE, "SQLITE");
        m.put(CBLError.Domain.FLEECE, "FLEECE");
        DOMAINS = Collections.unmodifiableMap(m);
    }
    @NonNull
    static String mapDomain(@Nullable String domain) {
        final String cDomain = DOMAINS.get(domain);
        return (cDomain != null) ? cDomain : DOMAIN_TESTSERVER;
    }

    public CblApiFailure(@NonNull CouchbaseLiteException cause) { this(cause.getMessage(), cause); }

    public CblApiFailure(@NonNull String message, @NonNull CouchbaseLiteException cause) {
        super(mapDomain(cause.getDomain()), cause.getCode(), message, cause);
    }
}
