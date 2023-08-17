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

import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

import com.couchbase.lite.Collection;
import com.couchbase.lite.Database;
import com.couchbase.lite.Document;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;


public class Snapshot {
    private static final String KEY_RESULT = "result";
    private static final String KEY_DESCRIPTION = "description";
    private static final String KEY_EXPECTED = "expected";
    private static final String KEY_ACTUAL = "actual";
    private static final String KEY_DOCUMENT = "document";

    private static final class Difference {
        public final String description;
        public final Object expected;
        public final Object actual;

        private Difference(
            @NonNull String description,
            @Nullable Object expected,
            @Nullable Object actual) {
            this.description = description;
            this.expected = expected;
            this.actual = actual;
        }
    }

    @NonNull
    private final DatabaseService dbSvc;

    public Snapshot(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    private final Map<String, Map<String, Document>> snapshot = new HashMap<>();

    public void snapshotDocument(
        @NonNull TestContext ctxt,
        @NonNull Database db,
        @NonNull String collFqn,
        @NonNull String docId) {
        final Map<String, Document> collSnapshot = snapshot.computeIfAbsent(collFqn, k -> new HashMap<>());
        if (collSnapshot.containsKey(docId)) { throw new ClientError("Attempt to snapshot doc twice: " + docId); }
        collSnapshot.put(docId, dbSvc.getDocOrNull(db, collFqn, docId, ctxt));
    }

    @NonNull
    public Map<String, Object> compare(
        @NonNull TestContext ctxt,
        @NonNull Database db,
        @NonNull Map<String, Map<String, Change>> delta) {
        final Map<String, Map<String, Document>> actual = clone(ctxt, db).snapshot;

        final Set<String> deltaCollections = new HashSet<>(delta.keySet());
        deltaCollections.removeAll(snapshot.keySet());
        if (!deltaCollections.isEmpty()) {
            throw new ClientError("Attempt to verify collections not in the snapshot: " + deltaCollections);
        }

        for (Map.Entry<String, Map<String, Document>> expectedColls: snapshot.entrySet()) {
            final String collFqn = expectedColls.getKey();
            final Map<String, Document> expectedColl = expectedColls.getValue();

            final Map<String, Change> collDelta = delta.get(collFqn);
            if (collDelta != null) {
                final Set<String> deltaDocs = new HashSet<>(collDelta.keySet());
                deltaDocs.removeAll(expectedColl.keySet());
                if (!deltaDocs.isEmpty()) {
                    throw new ClientError(
                        "Attempt to verify documents not in the snapshot (" + collFqn + "): " + deltaDocs);
                }
            }

            final Collection collection = dbSvc.getCollection(db, collFqn, ctxt);
            final Map<String, Document> actualCollection = actual.get(collFqn);
            for (Map.Entry<String, Document> docDesc: expectedColl.entrySet()) {
                final String docId = docDesc.getKey();
                Document expectedDoc = docDesc.getValue();

                final Change change = (collDelta == null) ? null : collDelta.get(docId);
                if (change != null) { expectedDoc = change.applyChange(collection, expectedDoc); }

                final Map<String, Object> resp
                    = compareDocs(change, collFqn, docId, expectedDoc, actualCollection.get(docId));
                if (resp != null) { return resp; }
            }
        }

        final Map<String, Object> resp = new HashMap<>();
        resp.put(KEY_DESCRIPTION, "Success");
        resp.put(KEY_RESULT, true);
        return resp;
    }

    @NonNull
    private Snapshot clone(@NonNull TestContext ctxt, @NonNull Database db) {
        final Snapshot clone = new Snapshot(dbSvc);
        for (Map.Entry<String, Map<String, Document>> collectionSnapshot: snapshot.entrySet()) {
            for (String docId: collectionSnapshot.getValue().keySet()) {
                clone.snapshotDocument(ctxt, db, collectionSnapshot.getKey(), docId);
            }
        }
        return clone;
    }

    @Nullable
    private Map<String, Object> compareDocs(
        @Nullable Change change,
        @NonNull String collFqn,
        @NonNull String docId,
        @Nullable Document expected,
        @Nullable Document actual) {
        if (expected == null) {
            if (actual == null) { return null; }
            final String msg;
            if (change == null) { msg = "should not exist"; }
            else if (change.type == Change.ChangeType.PURGE) { msg = "was not purged"; }
            else { msg = "was not deleted"; }
            return makeResp(msg, collFqn, docId);
        }

        if (actual == null) { return makeResp("was not found", collFqn, docId); }

        final Difference diff = compareTree(expected.toMap(), actual.toMap(), "");
        return (diff == null)
            ? null
            : makeResp(diff.description, collFqn, docId, diff.expected, diff.actual, actual);
    }

    @SuppressWarnings("unchecked")
    @Nullable
    private Difference compareTree(
        @NonNull Map<String, Object> expected,
        @NonNull Map<String, Object> actual,
        @NonNull String path) {

        final Set<String> allProps = new HashSet<>(actual.keySet());
        allProps.addAll(expected.keySet());

        for (String prop: allProps) {
            String propPath = path;
            if (path.length() > 2) { propPath += "."; }
            propPath += prop;

            final Object expectedVal = expected.get(prop);
            final Object actualVal = actual.get(prop);

            if (!expected.containsKey(prop)) {
                return new Difference("had unexpected properties at key '" + propPath + "'", null, actualVal);
            }

            if (!actual.containsKey(prop)) {
                return new Difference("had unexpected properties at key '" + propPath + "'", expectedVal, null);
            }

            if ((expectedVal instanceof Map) && (actualVal instanceof Map)) {
                final Difference diff
                    = compareTree((Map<String, Object>) expectedVal, (Map<String, Object>) actualVal, propPath);
                if (diff != null) { return diff; }
                continue;
            }

            if ((expectedVal instanceof List) && (actualVal instanceof List)) {
                final Difference diff = compareTree((List<Object>) expectedVal, (List<Object>) actualVal, propPath);
                if (diff != null) { return diff; }
                continue;
            }

            if (!Objects.equals(expectedVal, actualVal)) {
                return new Difference("had unexpected properties at key '" + propPath + "'", expectedVal, actualVal);
            }
        }

        return null;
    }

    @SuppressWarnings("unchecked")
    @Nullable
    private Difference compareTree(@NonNull List<Object> expected, @NonNull List<Object> actual, @NonNull String path) {
        final int nActual = actual.size();
        final int nExpected = expected.size();
        final int n = Math.max(nExpected, nActual);
        for (int i = 0; i < n; i++) {
            String propPath = path + "[" + i + "]";

            if (i >= nExpected) {
                return new Difference(
                    "had unexpected properties at key '" + propPath + "'",
                    null,
                    actual.get(i));
            }
            final Object expectedVal = expected.get(i);

            if (i >= nActual) {
                return new Difference(
                    "had unexpected properties at key '" + propPath + "'",
                    expected.get(i),
                    null);
            }
            final Object actualVal = actual.get(i);

            if ((expectedVal instanceof Map) && (actualVal instanceof Map)) {
                final Difference diff
                    = compareTree((Map<String, Object>) expectedVal, (Map<String, Object>) actualVal, propPath);
                if (diff != null) { return diff; }
                continue;
            }

            if ((expectedVal instanceof List) && (actualVal instanceof List)) {
                final Difference diff = compareTree((List<Object>) expectedVal, (List<Object>) actualVal, propPath);
                if (diff != null) { return diff; }
                continue;
            }

            if (!Objects.equals(expectedVal, actualVal)) {
                return new Difference("had unexpected properties at key '" + propPath + "'", expectedVal, actualVal);
            }
        }

        return null;
    }

    @NonNull
    private Map<String, Object> makeResp(
        @NonNull String msg,
        @NonNull String collFqn,
        @Nullable String docId) {
        final Map<String, Object> resp = new HashMap<>();
        resp.put(KEY_DESCRIPTION, "Document '" + docId + "' in '" + collFqn + "' " + msg);
        resp.put(KEY_RESULT, false);
        return resp;
    }

    @NonNull
    private Map<String, Object> makeResp(
        @NonNull String msg,
        @NonNull String collFqn,
        @Nullable String docId,
        @Nullable Object expected,
        @Nullable Object actual,
        @Nullable Document doc) {
        final Map<String, Object> resp = makeResp(msg, collFqn, docId);
        if (expected != null) { resp.put(KEY_EXPECTED, expected); }
        if (actual != null) { resp.put(KEY_ACTUAL, actual); }
        if (doc != null) { resp.put(KEY_DOCUMENT, doc.toMap()); }
        return resp;
    }
}

