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
package com.couchbase.lite.mobiletest.endpoints.v1;

import androidx.annotation.NonNull;

import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.services.DatabaseService;


@SuppressWarnings({"PMD.UnusedPrivateField", "PMD.SingularField"})
public class VerifyDocs {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_SNAPSHOT = "snapshot";
    private static final String KEY_CHANGES = "changes";
    private static final String KEY_TYPE = "type";
    private static final String KEY_COLLECTION = "description";
    private static final String KEY_DOC_ID = "documentID";
    private static final String KEY_UPDATES = "updatedProperties";
    private static final String KEY_REMOVES = "removedProperties";

    private static final String KEY_RESULT = "result";
    private static final String KEY_DESCRIPTION = "description";

    private static final Set<String> LEGAL_VALIDATE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_SNAPSHOT);
        l.add(KEY_CHANGES);
        LEGAL_VALIDATE_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_UPDATE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_TYPE);
        l.add(KEY_COLLECTION);
        l.add(KEY_DOC_ID);
        l.add(KEY_UPDATES);
        l.add(KEY_REMOVES);
        LEGAL_UPDATE_KEYS = Collections.unmodifiableSet(l);
    }

    @NonNull
    private final DatabaseService dbSvc;

    public VerifyDocs(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    public Map<String, Object> verify(@NonNull TypedMap req, @NonNull TestContext ctxt) {
        final Map<String, Object> resp = new HashMap<>();
        resp.put(KEY_RESULT, true);
        resp.put(KEY_DESCRIPTION, "all good");
        return resp;
    }
}
