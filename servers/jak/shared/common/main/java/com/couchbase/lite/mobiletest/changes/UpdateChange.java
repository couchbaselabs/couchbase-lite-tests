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

import java.util.List;
import java.util.Map;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Document;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.services.DatabaseService;


public final class UpdateChange extends Change {
    @NonNull
    private final Map<String, Object> updates;
    @NonNull
    private final List<String> deletions;

    public UpdateChange(@NonNull String docId, @NonNull Map<String, Object> updates, @NonNull List<String> deletions) {
        super(ChangeType.UPDATE, docId);
        this.updates = updates;
        this.deletions = deletions;
    }


    @Override
    @NonNull
    public MutableDocument applyChange(@NonNull Collection collection, @Nullable Document doc) {
        final KeypathParser parser = new KeypathParser();

        final MutableDocument mDoc = (doc != null) ? doc.toMutable() : new MutableDocument(docId);
        final Map<String, Object> data = mDoc.toMap();

        for (Map.Entry<String, Object> change: updates.entrySet()) {
            parser.parse(change.getKey()).set(data, change.getValue());
        }

        for (String deletion: deletions) { parser.parse(deletion).delete(data); }

        return mDoc.setData(data);
    }

    @Override
    public void updateDocument(@NonNull DatabaseService dbSvc, @NonNull Collection collection) {
        final Document doc = dbSvc.getDocOrNull(collection, docId);
        try { collection.save(applyChange(collection, doc)); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed saving updated document", e); }
    }
}
