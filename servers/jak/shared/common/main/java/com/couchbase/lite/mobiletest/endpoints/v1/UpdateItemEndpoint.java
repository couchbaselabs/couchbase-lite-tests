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

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.mobiletest.changes.Change;
import com.couchbase.lite.mobiletest.changes.DeleteChange;
import com.couchbase.lite.mobiletest.changes.PurgeChange;
import com.couchbase.lite.mobiletest.changes.UpdateChange;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public abstract class UpdateItemEndpoint {
    protected static final String KEY_REMOVED_PROPS = "removedProperties";
    protected static final String KEY_UPDATE_PROPS = "updatedProperties";
    protected static final String KEY_UPDATE_BLOBS = "updatedBlobs";

    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_DOC_ID = "documentID";
    private static final String KEY_TYPE = "type";
    private static final String TYPE_UPDATE = "update";
    private static final String TYPE_DELETE = "delete";
    private static final String TYPE_PURGE = "purge";

    private static final Set<String> LEGAL_UPDATE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_TYPE);
        l.add(KEY_COLLECTION);
        l.add(KEY_DOC_ID);
        l.add(KEY_REMOVED_PROPS);
        l.add(KEY_UPDATE_PROPS);
        l.add(KEY_UPDATE_BLOBS);
        LEGAL_UPDATE_KEYS = Collections.unmodifiableSet(l);
    }

    @NonNull
    protected final DatabaseService dbSvc;

    protected UpdateItemEndpoint(@NonNull DatabaseService svc) { dbSvc = svc; }

    @NonNull
    public Map<String, Map<String, Change>> getDelta(@NonNull TypedList updates) {
        // Collection Name -> DocId -> Change
        final Map<String, Map<String, Change>> delta = new HashMap<>();
        final int n = updates.size();
        for (int i = 0; i < n; i++) {
            final TypedMap change = updates.getMap(i);
            if (change == null) { throw new ServerError("Change is empty"); }
            change.validate(LEGAL_UPDATE_KEYS);

            final String collName = change.getString(KEY_COLLECTION);
            if (collName == null) { throw new ClientError("Verify docs request is missing collection name"); }

            final String docId = change.getString(KEY_DOC_ID);
            if (docId == null) { throw new ClientError("Verify docs request is missing a document id"); }

            final String changeType = change.getString(KEY_TYPE);
            if (changeType == null) { throw new ClientError("Update has no type"); }

            final Change ch;
            switch (changeType.toLowerCase(Locale.getDefault())) {
                case TYPE_DELETE:
                    ch = new DeleteChange(docId);
                    break;
                case TYPE_PURGE:
                    ch = new PurgeChange(docId);
                    break;
                case TYPE_UPDATE:
                    ch = new UpdateChange(docId, getDeletions(change), getUpdates(change), getBlobs(change));
                    break;
                default:
                    throw new ClientError("Unrecognized update type: " + changeType);
            }

            delta.computeIfAbsent(collName, k -> new HashMap<>()).put(docId, ch);
        }

        return delta;
    }

    @NonNull
    private List<String> getDeletions(@NonNull TypedMap update) {
        final List<String> parsedDeletions = new ArrayList<>();
        final TypedList deletions = update.getList(KEY_REMOVED_PROPS);
        if (deletions != null) {
            final int m = deletions.size();
            for (int j = 0; j < m; j++) {
                final String path = deletions.getString(j);
                if (path == null) { throw new ServerError("Null removal"); }
                parsedDeletions.add(path);
            }
        }
        return parsedDeletions;
    }

    @NonNull
    private Map<String, Object> getUpdates(@NonNull TypedMap update) {
        final Map<String, Object> parsedChanges = new HashMap<>();
        final TypedList changes = update.getList(KEY_UPDATE_PROPS);
        if (changes != null) {
            final int m = changes.size();
            for (int j = 0; j < m; j++) {
                final TypedMap change = changes.getMap(j);
                if (change == null) { throw new ServerError("Null update"); }
                for (String path: change.getKeys()) { parsedChanges.put(path, change.getObject(path)); }
            }
        }
        return parsedChanges;
    }

    @NonNull
    private Map<String, String> getBlobs(@NonNull TypedMap update) {
        final Map<String, String> parsedBlobs = new HashMap<>();
        final TypedMap blobs = update.getMap(KEY_UPDATE_BLOBS);
        if (blobs != null) {
            for (String path: blobs.getKeys()) { parsedBlobs.put(path, blobs.getString(path)); }
        }
        return parsedBlobs;
    }
}
