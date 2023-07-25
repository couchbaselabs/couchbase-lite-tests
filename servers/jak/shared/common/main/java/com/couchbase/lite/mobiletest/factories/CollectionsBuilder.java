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
import androidx.annotation.Nullable;

import java.util.HashSet;
import java.util.Set;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.mobiletest.data.TypedList;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;


public class CollectionsBuilder {
    @Nullable
    private final TypedList collFqns;
    @NonNull
    private final Database db;

    public CollectionsBuilder(@Nullable TypedList collFqns, @NonNull Database db) {
        this.collFqns = collFqns;
        this.db = db;
    }

    @NonNull
    public Set<Collection> build() {
        if (collFqns == null) { throw new ClientError("Replication collection doesn't specify collection names"); }

        final Set<Collection> collections = new HashSet<>();
        for (int j = 0; j < collFqns.size(); j++) {
            final String collFqn = collFqns.getString(j);
            if (collFqn == null) { throw new ClientError("Empty collection name (" + j + ")"); }

            final String[] collName = collFqn.split("\\.");
            if ((collName.length != 2) || collName[0].isEmpty() || collName[1].isEmpty()) {
                throw new ClientError("Cannot parse collection name: " + collFqn);
            }

            final Collection collection;
            try { collection = db.getCollection(collName[1], collName[0]); }
            catch (CouchbaseLiteException e) {
                throw new CblApiFailure("Failed retrieving collection: " + collFqn, e);
            }
            collections.add(collection);
        }

        return collections;
    }
}
