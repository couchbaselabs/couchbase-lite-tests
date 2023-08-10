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
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.DataSource;
import com.couchbase.lite.Meta;
import com.couchbase.lite.QueryBuilder;
import com.couchbase.lite.Result;
import com.couchbase.lite.ResultSet;
import com.couchbase.lite.SelectResult;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.tools.CollectionsBuilder;


public class GetAllDocsV1 {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_COLLECTIONS = "collections";

    private static final String KEY_ID = "id";
    private static final String KEY_REV = "rev";

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
        try (CollectionsBuilder colls = new CollectionsBuilder(
            req.getList(KEY_COLLECTIONS),
            dbSvc.getNamedDb(req, mem))) {
            return getAllDocs(colls.getCollections());
        }
    }

    @NonNull
    private Map<String, Object> getAllDocs(Set<Collection> collections) {
        final Map<String, Object> colls = new HashMap<>();
        for (Collection collection: collections) {
            final String collectionName = collection.getScope().getName() + "." + collection.getName();

            final List<Result> results;
            try (ResultSet rs = QueryBuilder.select(
                    SelectResult.expression(Meta.id).as(KEY_ID),
                    SelectResult.expression(Meta.revisionID).as(KEY_REV))
                .from(DataSource.collection(collection))
                .execute()) {
                results = rs.allResults();
            }
            catch (CouchbaseLiteException err) {
                throw new CblApiFailure("Failed querying docs for collection: " + collectionName, err);
            }

            final List<Map<String, String>> docs = new ArrayList<>();
            for (Result result: results) {
                final Map<String, String> doc = new HashMap<>();
                doc.put(KEY_ID, result.getString(KEY_ID));
                doc.put(KEY_REV, result.getString(KEY_REV));
                docs.add(doc);
            }

            colls.put(collectionName, docs);
        }

        return colls;
    }
}
