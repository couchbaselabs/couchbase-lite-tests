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

import com.couchbase.lite.Document;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public class GetDocument {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_DOCUMENTS = "document";
    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_DOC_ID = "id";
    private static final String KEY_META_DOC_ID = "_id";
    private static final String KEY_META_REV_HISTORY = "_revs";


    private static final Set<String> LEGAL_GET_DOC_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_DOCUMENTS);
        LEGAL_GET_DOC_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_DOC_SPEC_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_COLLECTION);
        l.add(KEY_DOC_ID);
        LEGAL_DOC_SPEC_KEYS = Collections.unmodifiableSet(l);
    }


    @NonNull
    private final DatabaseService dbSvc;

    public GetDocument(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    public Map<String, Object> getDocument(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_GET_DOC_KEYS);

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("No database specified for getDocument"); }

        final TypedMap docSpec = req.getMap(KEY_DOCUMENTS);
        if (docSpec == null) { throw new ClientError("No document specified for getDocument"); }
        docSpec.validate(LEGAL_DOC_SPEC_KEYS);

        final String collectionName = docSpec.getString(KEY_COLLECTION);
        if (collectionName == null) { throw new ClientError("No collection specified for getDocument"); }

        final String docId = docSpec.getString(KEY_DOC_ID);
        if (docId == null) { throw new ClientError("No document id specified for getDocument"); }

        final Document doc = dbSvc.getDocument(ctxt, dbName, collectionName, docId);

        final Map<String, Object> ret = doc.toMap();
        ret.put(KEY_META_DOC_ID, doc.getId());
        ret.put(KEY_META_REV_HISTORY, dbSvc.getRevisionHistory(doc));

        return ret;
    }
}
