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
import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.Document;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.data.KeypathParser;
import com.couchbase.lite.mobiletest.data.TypedList;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;


public class UpdateDb {
    private static final String KEY_TYPE = "type";
    private static final String TYPE_UPDATE = "update";
    private static final String TYPE_DELETE = "delete";
    private static final String TYPE_PURGE = "purge";

    private static final String KEY_DATABASE = "database";
    private static final String KEY_UPDATES = "updates";
    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_DOC_ID = "documentID";
    private static final String KEY_UPDATE_PROPS = "updatedProperties";
    private static final String KEY_REMOVED_PROPS = "removedProperties";

    private static final List<String> LEGAL_UPDATES_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_DATABASE);
        l.add(KEY_UPDATES);
        LEGAL_UPDATES_KEYS = Collections.unmodifiableList(l);
    }

    private static final List<String> LEGAL_UPDATE_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_TYPE);
        l.add(KEY_COLLECTION);
        l.add(KEY_DOC_ID);
        l.add(KEY_UPDATE_PROPS);
        l.add(KEY_REMOVED_PROPS);
        LEGAL_UPDATE_KEYS = Collections.unmodifiableList(l);
    }


    @NonNull
    private final DatabaseService dbSvc;

    public UpdateDb(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    public Map<String, Object> updateDb(@NonNull TypedMap req, @NonNull TestContext ctxt) {
        req.validate(LEGAL_UPDATES_KEYS);

        final TypedList updates = req.getList(KEY_UPDATES);
        if (updates == null) { throw new ClientError("Database update request has no updates"); }

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("All Docs request doesn't specify a database"); }

        final Database db = dbSvc.getOpenDb(ctxt, dbName);
        final int n = updates.size();
        for (int i = 0; i < n; i++) {
            final TypedMap update = updates.getMap(i);
            if (update == null) { throw new ServerError("Null update request"); }
            update.validate(LEGAL_UPDATE_KEYS);

            final String collectionName = update.getString(KEY_COLLECTION);
            if (collectionName == null) { throw new ClientError("Database update request is missing collection name"); }

            final String id = update.getString(KEY_DOC_ID);
            if (id == null) { throw new ClientError("Database update request is missing a document id"); }

            final Collection collection = dbSvc.getCollection(db, collectionName, ctxt);

            final Document doc;
            try { doc = collection.getDocument(id); }
            catch (CouchbaseLiteException e) {
                throw new CblApiFailure("Failed retrieving document: " + id + " from collection " + collectionName, e);
            }

            final String updateType = update.getString(KEY_TYPE);
            if (updateType == null) { throw new ClientError("Update has no type"); }
            switch (updateType.toLowerCase(Locale.getDefault())) {
                case TYPE_DELETE:
                    deleteDocument(doc, collection);
                    break;
                case TYPE_PURGE:
                    purgeDocument(doc, collection);
                    break;
                case TYPE_UPDATE:
                    updateDocument((doc != null) ? doc.toMutable() : new MutableDocument(id), update, collection);
                    break;
                default:
                    throw new ClientError("Unrecognized update type: " + updateType);
            }
        }

        return Collections.emptyMap();
    }

    private void deleteDocument(@Nullable Document doc, @NonNull Collection collection) {
        if (doc == null) { return; }
        try { collection.delete(doc); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed deleting document", e); }
    }

    private void purgeDocument(@Nullable Document doc, @NonNull Collection collection) {
        if (doc == null) { return; }
        try { collection.purge(doc); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed purging document", e); }
    }

    private void updateDocument(@NonNull MutableDocument mDoc, @NonNull TypedMap update, @NonNull Collection coll) {
        final Map<String, Object> data = mDoc.toMap();

        final KeypathParser parser = new KeypathParser();

        final TypedList changes = update.getList(KEY_UPDATE_PROPS);
        if (changes != null) {
            final int m = changes.size();
            for (int j = 0; j < m; j++) {
                final TypedMap change = changes.getMap(j);
                if (change == null) { throw new ServerError("Null update"); }
                for (String path: change.getKeys()) { parser.parse(path).set(data, change.getObject(path)); }
            }
        }

        final TypedList removals = update.getList(KEY_REMOVED_PROPS);
        if (removals != null) {
            final int m = removals.size();
            for (int j = 0; j < m; j++) {
                final String path = removals.getString(j);
                if (path == null) { throw new ServerError("Null removal"); }
                parser.parse(path).delete(data);
            }
        }

        try { coll.save(mDoc.setData(data)); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed saving updated document", e); }
    }
}
