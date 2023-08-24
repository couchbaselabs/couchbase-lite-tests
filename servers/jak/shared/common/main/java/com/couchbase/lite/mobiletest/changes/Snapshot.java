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

import java.util.ArrayList;
import java.util.Collections;
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
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;


public class Snapshot {
    public static final class Difference {
        @NonNull
        public final String collFqn;
        @NonNull
        public final String docId;
        @Nullable
        public final Map<String, Object> content;
        @Nullable
        public final String keyPath;
        @Nullable
        public final Object expected;
        @Nullable
        public final Object actual;
        @Nullable
        public final String type;
        @NonNull
        public final String description;

        @SuppressWarnings("PMD.StringToString")
        private Difference(
            @NonNull String collFqn,
            @NonNull String docId,
            @Nullable Map<String, Object> content,
            @Nullable String keyPath,
            @Nullable Object expected,
            @Nullable Object actual,
            @Nullable Change change,
            @NonNull String description) {
            this.collFqn = collFqn;
            this.docId = docId;
            this.content = (content == null) ? null : Collections.unmodifiableMap(content);
            this.keyPath = keyPath;
            this.expected = expected;
            this.actual = actual;
            this.type = (change == null) ? null : change.type.toString();
            this.description = description;
        }

        @Override
        @NonNull
        public String toString() {
            return "@" + collFqn + "." + docId + "$" + keyPath + ": "
                + type + "(" + expected + " => " + actual + ")" + " " + description;
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
    public List<Difference> compare(
        @NonNull TestContext ctxt,
        @NonNull Database db,
        @NonNull Map<String, Map<String, Change>> delta) {
        final List<Difference> diffs = new ArrayList<>();
        final Map<String, Map<String, Document>> actual = clone(ctxt, db).snapshot;

        // all the collections named in either the snapshot or the delta
        final Set<String> collections = new HashSet<>(snapshot.keySet());
        collections.addAll(delta.keySet());
        for (String collFqn: collections) {
            if ((!snapshot.containsKey(collFqn)) || (!actual.containsKey(collFqn))) {
                throw new ClientError("Attempt to verify a collection not in the snapshot: " + collFqn);
            }
            final Map<String, Document> originalDocs = snapshot.get(collFqn);
            final Map<String, Document> currentDocs = actual.get(collFqn);
            if ((originalDocs == null) || (currentDocs == null)) {
                throw new ServerError("Null doc map in snapshot for collection: " + collFqn);
            }

            // if there are no changes in this collection, there are no changes to any doc in this collection
            Map<String, Change> docDeltas = delta.get(collFqn);
            if (docDeltas == null) { docDeltas = new HashMap<>(); }

            final Collection collection = dbSvc.getCollection(db, collFqn, ctxt);

            // all the docs named in either the snapshot or the delta
            final Set<String> docIds = new HashSet<>(originalDocs.keySet());
            docIds.addAll(docDeltas.keySet());
            for (String docId: docIds) {
                if ((!originalDocs.containsKey(docId)) || (!currentDocs.containsKey(docId))) {
                    throw new ClientError("Attempt to verify a document not in the snapshot: " + collFqn + "." + docId);
                }

                Document originalDoc = originalDocs.get(docId);
                final Document currentDoc = currentDocs.get(docId);

                final Change change = docDeltas.get(docId);
                if (change != null) { originalDoc = change.applyChange(collection, originalDoc); }

                // the originalDoc is now the expected
                // and currentDoc is the actual
                compareDoc(collFqn, docId, originalDoc, currentDoc, change, diffs);
            }
        }

        return diffs;
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

    private void compareDoc(
        @NonNull String collFqn,
        @NonNull String docId,
        @Nullable Document expected,
        @Nullable Document actual,
        @Nullable Change change,
        List<Difference> diffs
    ) {
        if (expected == null) {
            if (actual != null) {
                diffs.add(
                    new Difference(
                        collFqn,
                        docId,
                        null,
                        null,
                        null,
                        docId,
                        change,
                        "Document should not exist"));
            }
            return;
        }

        if (actual == null) {
            diffs.add(new Difference(
                collFqn,
                docId,
                null,
                null,
                null,
                docId,
                change,
                "Document was not found"));
            return;
        }

        // at this point, the two documents should be identical
        final Map<String, Object> actualContent = actual.toMap();
        compareDocContent(collFqn, docId, actualContent, "", expected.toMap(), actualContent, change, diffs);
    }

    @SuppressWarnings("unchecked")
    private void compareDocContent(
        @NonNull String collFqn,
        @NonNull String docId,
        @NonNull Map<String, Object> doc,
        @NonNull String path,
        @NonNull Map<String, Object> expected,
        @NonNull Map<String, Object> actual,
        @Nullable Change change,
        @NonNull List<Difference> diffs) {
        final Set<String> allProps = new HashSet<>(actual.keySet());
        allProps.addAll(expected.keySet());
        for (String prop: allProps) {
            String propPath = path;
            if (path.length() > 2) { propPath += "."; }
            propPath += prop;

            final Object expectedVal = expected.get(prop);
            final Object actualVal = actual.get(prop);

            if (!expected.containsKey(prop)) {
                if (actual.containsKey(prop)) {
                    diffs.add(new Difference(
                        collFqn,
                        docId,
                        doc,
                        propPath,
                        expectedVal,
                        actualVal,
                        change,
                        "Missing property"));
                }
                continue;
            }

            if (!actual.containsKey(prop)) {
                diffs.add(new Difference(
                    collFqn,
                    docId,
                    doc,
                    propPath,
                    expectedVal,
                    actualVal,
                    change,
                    "Unexpected property"));
                continue;
            }

            if ((expectedVal instanceof Map) && (actualVal instanceof Map)) {
                compareDocContent(
                    collFqn,
                    docId,
                    doc,
                    propPath,
                    (Map<String, Object>) expectedVal,
                    (Map<String, Object>) actualVal,
                    change,
                    diffs);
                continue;
            }

            if ((expectedVal instanceof List) && (actualVal instanceof List)) {
                compareDocContent(
                    collFqn,
                    docId,
                    doc,
                    propPath,
                    (List<Object>) expectedVal,
                    (List<Object>) actualVal,
                    change,
                    diffs);
                continue;
            }

            if (!Objects.equals(expectedVal, actualVal)) {
                diffs.add(
                    new Difference(
                        collFqn,
                        docId,
                        doc,
                        propPath,
                        expectedVal,
                        actualVal,
                        change,
                        "Property values are different"));
            }
        }
    }

    @SuppressWarnings("unchecked")
    private void compareDocContent(
        @NonNull String collFqn,
        @NonNull String docId,
        @NonNull Map<String, Object> doc,
        @NonNull String path,
        @NonNull List<Object> expected,
        @NonNull List<Object> actual,
        @Nullable Change change,
        @NonNull List<Difference> diffs) {
        final int nExpected = expected.size();
        final int nActual = actual.size();
        final int n = Math.max(nExpected, nActual);
        for (int i = 0; i < n; i++) {
            final String idxPath = path + "[" + i + "]";

            final Object expectedVal = (i >= nExpected) ? null : expected.get(i);
            final Object actualVal = (i >= nActual) ? null : actual.get(i);

            if (i >= nExpected) {
                diffs.add(
                    new Difference(
                        collFqn,
                        docId,
                        doc,
                        idxPath,
                        null,
                        actualVal,
                        change,
                        "Unexpected array value"));
                continue;
            }

            if (i >= nActual) {
                diffs.add(
                    new Difference(
                        collFqn,
                        docId,
                        doc,
                        idxPath,
                        expected,
                        null,
                        change,
                        "Missing array value"));
                continue;
            }

            if ((expectedVal instanceof Map) && (actualVal instanceof Map)) {
                compareDocContent(
                    collFqn,
                    docId,
                    doc,
                    idxPath,
                    (Map<String, Object>) expectedVal,
                    (Map<String, Object>) actualVal,
                    change,
                    diffs);
                continue;
            }

            if ((expectedVal instanceof List) && (actualVal instanceof List)) {
                compareDocContent(
                    collFqn,
                    docId,
                    doc,
                    idxPath,
                    (List<Object>) expectedVal,
                    (List<Object>) actualVal,
                    change,
                    diffs);
                continue;
            }

            if (!Objects.equals(expectedVal, actualVal)) {
                diffs.add(
                    new Difference(
                        collFqn,
                        docId,
                        doc,
                        idxPath,
                        expectedVal,
                        actualVal,
                        change,
                        "Array values are different"));
            }
        }
    }
}

