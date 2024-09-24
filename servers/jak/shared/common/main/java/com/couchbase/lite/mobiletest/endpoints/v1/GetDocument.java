//
// Copyright (c) 2024 Couchbase, Inc All rights reserved.
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
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public class GetDocument {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_DOC_ID = "id";

    private static final Set<String> LEGAL_GET_DOCUMENT_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_COLLECTION);
        l.add(KEY_DOC_ID);
        LEGAL_GET_DOCUMENT_KEYS = Collections.unmodifiableSet(l);
    }

    @NonNull
    private final DatabaseService dbSvc;

    public GetDocument(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    public Map<String, Object> getDocument(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_GET_DOCUMENT_KEYS);

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("No database specified for getDocument"); }

        final String collectionName = req.getString(KEY_COLLECTION);
        if (collectionName == null) { throw new ClientError("No collection specified for getDocument"); }

        final String docId = req.getString(KEY_DOC_ID);
        if (docId == null) { throw new ClientError("No document id specified for getDocument"); }

        return dbSvc.getDocument(ctxt, dbName, collectionName, docId);
    }
}
