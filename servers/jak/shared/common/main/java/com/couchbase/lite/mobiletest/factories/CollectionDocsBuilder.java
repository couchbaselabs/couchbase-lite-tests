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
package com.couchbase.lite.mobiletest.factories;

import androidx.annotation.NonNull;

import java.util.ArrayList;
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
import com.couchbase.lite.mobiletest.errors.CblApiFailure;


public class CollectionDocsBuilder {
    private static final String KEY_ID = "id";
    private static final String KEY_REV = "rev";

    @NonNull
    private final Set<Collection> collections;

    public CollectionDocsBuilder(@NonNull Set<Collection> collections) { this.collections = collections; }

    @NonNull
    public Map<String, Object> build() {
        final Map<String, Object> colls = new HashMap<>();
        for (Collection collection: collections) {
            final String collectionName = collection.getScope() + "." + collection.getName();

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
