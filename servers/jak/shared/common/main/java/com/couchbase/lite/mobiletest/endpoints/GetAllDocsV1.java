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
package com.couchbase.lite.mobiletest.endpoints;

import androidx.annotation.NonNull;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.tools.CollectionDocsBuilder;
import com.couchbase.lite.mobiletest.tools.CollectionsBuilder;


public class GetAllDocsV1 {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_COLLECTIONS = "collections";

    private static final List<String> LEGAL_COLLECTION_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_DATABASE);
        l.add(KEY_COLLECTIONS);
        LEGAL_COLLECTION_KEYS = Collections.unmodifiableList(l);
    }


    @NonNull
    private final DatabaseService dbSvc;

    public GetAllDocsV1(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    public Map<String, Object> getAllDocs(@NonNull TypedMap req, @NonNull Memory mem) {
        req.validate(LEGAL_COLLECTION_KEYS);
        try (CollectionsBuilder builder
                 = new CollectionsBuilder(req.getList(KEY_COLLECTIONS), dbSvc.getNamedDb(req, mem))) {
            return new CollectionDocsBuilder(builder.getCollections()).build();
        }
    }
}
