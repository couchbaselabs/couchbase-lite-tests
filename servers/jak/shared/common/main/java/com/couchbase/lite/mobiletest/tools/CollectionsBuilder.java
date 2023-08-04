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
package com.couchbase.lite.mobiletest.tools;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.HashSet;
import java.util.Set;

import com.couchbase.lite.Collection;
import com.couchbase.lite.Database;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.data.TypedList;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;


// Consider some way of closeing these at the end of a request.
public class CollectionsBuilder implements AutoCloseable {
    @NonNull
    private final TypedList collFqns;
    @NonNull
    private final Database db;
    @NonNull
    private final DatabaseService dbSvc;
    @NonNull
    private final Set<Collection> collections = new HashSet<>();

    public CollectionsBuilder(@Nullable TypedList collFqns, @NonNull Database db) {
        if (collFqns == null) { throw new ClientError("Replication collection doesn't specify collection names"); }
        this.collFqns = collFqns;
        this.db = db;
        this.dbSvc = TestApp.getApp().getDbSvc();
    }

    public void close() { for (Collection collection: collections) { collection.close(); } }

    public Set<Collection> getCollections() {
        if (collections.isEmpty()) {
            for (int j = 0; j < collFqns.size(); j++) {
                final String collFqn = collFqns.getString(j);
                if (collFqn == null) { throw new ClientError("Empty collection name (" + j + ")"); }
                collections.add(dbSvc.getCollection(db, collFqn));
            }
        }
        return new HashSet<>(collections);
    }
}
