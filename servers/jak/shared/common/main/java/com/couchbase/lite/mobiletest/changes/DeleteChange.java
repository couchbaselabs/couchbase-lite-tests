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
package com.couchbase.lite.mobiletest.changes;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Document;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.services.DatabaseService;


public final class DeleteChange extends Change {
    public DeleteChange(@NonNull String collFqn, @NonNull String docId) {
        super(ChangeType.DELETE, collFqn, docId);
    }

    @Override
    @Nullable
    public MutableDocument applyChange(@NonNull Collection collection, @Nullable Document mDoc) { return null; }

    @Override
    public void updateDocument(@NonNull DatabaseService dbSvc, @NonNull Collection collection) {
        final Document doc = dbSvc.getDocument(collection, docId);
        try { collection.purge(doc); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed purging document", e); }
    }
}
