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
package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.DatabaseConfiguration;
import com.couchbase.lite.Document;
import com.couchbase.lite.internal.core.C4Database;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public final class DatabaseService {
    private static final String TAG = "DB_SVC";

    private static final String ZIP_EXTENSION = ".zip";
    private static final String DB_EXTENSION = C4Database.DB_EXTENSION;

    private static final String KEY_DATASETS = "datasets";

    private static final Set<String> LEGAL_DATASET_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATASETS);
        LEGAL_DATASET_KEYS = Collections.unmodifiableSet(l);
    }
    // Instance methods


    public void init(TypedMap req, TestContext ctxt) {
        final TestApp app = TestApp.getApp();

        final String testDir = "tests_" + StringUtils.randomString(6);
        final File dbDir = new File(app.getFilesDir(), testDir);
        if (!dbDir.mkdirs() || !dbDir.canWrite()) {
            throw new ServerError("Could not create db dir on init: " + dbDir);
        }
        ctxt.setDbDir(dbDir);

        req.validate(LEGAL_DATASET_KEYS);
        final TypedMap datasets = req.getMap(KEY_DATASETS);
        if (datasets == null) { throw new ClientError("Missing dataset specification in init"); }
        for (String dataset: datasets.getKeys()) {
            final TypedList databases = datasets.getList(dataset);
            if (databases == null) {
                throw new ClientError("Missing target databases in dataset " + dataset + " in init");
            }
            for (int i = 0; i < databases.size(); i++) {
                final String dbName = databases.getString(i);
                if (dbName == null) {
                    throw new ClientError("Empty target databases in dataset " + dataset + " in init");
                }
                installDataset(dataset, dbName, ctxt);
            }
        }
    }

    @NonNull
    public Database getOpenDb(@NonNull TestContext ctxt, @NonNull String dbName) {
        final Database db = ctxt.getDb(dbName);
        if (db == null) { throw new ClientError("Database not open: " + dbName); }
        return db;
    }

    public void closeDb(@NonNull String name, @NonNull TestContext ctxt) {
        if (closeDbInternal(name, ctxt)) { return; }
        Log.w(TAG, "Attempt to close a database that is not open: " + name);
    }

    @NonNull
    public Set<Collection> getCollections(
        @NonNull Database db,
        @NonNull TypedList collFqns,
        @NonNull TestContext ctxt) {
        final Set<Collection> collections = new HashSet<>();
        for (int j = 0; j < collFqns.size(); j++) {
            final String collFqn = collFqns.getString(j);
            if (collFqn == null) { throw new ClientError("Empty collection name (" + j + ")"); }
            collections.add(getCollection(db, collFqn, ctxt));
        }
        return collections;
    }

    @NonNull
    public Collection getCollection(@NonNull Database db, @NonNull String collFqn, @NonNull TestContext ctxt) {
        final String[] collName = collFqn.split("\\.");
        if ((collName.length != 2) || collName[0].isEmpty() || collName[1].isEmpty()) {
            throw new ClientError("Cannot parse collection name: " + collFqn);
        }

        final Collection collection;
        try { collection = db.getCollection(collName[1], collName[0]); }
        catch (CouchbaseLiteException e) {
            throw new CblApiFailure("Failed retrieving collection: " + collFqn + " from db " + db.getName(), e);
        }
        if (collection == null) {
            throw new ClientError("Database " + db.getName() + " does not contain collection " + collFqn);
        }

        ctxt.addOpenCollection(collection);

        return collection;
    }

    @NonNull
    public Document getDocument(
        @NonNull Database db,
        @NonNull String collFqn,
        @NonNull String docId,
        @NonNull TestContext ctxt) {
        final Document doc = getDocOrNull(db, collFqn, docId, ctxt);
        if (doc == null) { throw new ClientError("Document not found: " + docId); }
        return doc;
    }

    @NonNull
    public Document getDocument(@NonNull Collection collection, @NonNull String docId) {
        final Document doc = getDocOrNull(collection, docId);
        if (doc == null) { throw new ClientError("Document not found: " + docId); }
        return doc;
    }

    @Nullable
    public Document getDocOrNull(
        @NonNull Database db,
        @NonNull String collFqn,
        @NonNull String docId,
        @NonNull TestContext ctxt) {
        return getDocOrNull(getCollection(db, collFqn, ctxt), docId);
    }


    @Nullable
    public Document getDocOrNull(@NonNull Collection collection, @NonNull String docId) {
        try { return collection.getDocument(docId); }
        catch (CouchbaseLiteException e) {
            throw new CblApiFailure("Failed getting doc " + docId + " from collection " + collection, e);
        }
    }


    // New stream constructors are supported only in API 26+
    private void installDataset(@NonNull String datasetName, @NonNull String dbName, @NonNull TestContext ctxt) {
        final File dbDir = ctxt.getDbDir();
        if (dbDir == null) { throw new ServerError("Cannot find test directory on install dataset"); }

        final String dbFullName = datasetName + DB_EXTENSION;
        if (new File(dbDir, dbFullName).exists()) { throw new ClientError("Database already exists: " + dbName); }

        final FileUtils fileUtils = new FileUtils();

        final File unzipDir = new File(dbDir, "tmp");
        if (unzipDir.exists() && !fileUtils.deleteRecursive(unzipDir)) {
            throw new ServerError("Failed deleting unzip tmp directory");
        }
        if (!unzipDir.mkdirs()) { throw new ServerError("Failed creating unzip tmp directory"); }

        try (InputStream in = TestApp.getApp().getAsset(dbFullName + ZIP_EXTENSION)) {
            if (in == null) { throw new ServerError("Can't open resource " + dbFullName + ZIP_EXTENSION); }
            fileUtils.unzip(in, unzipDir);
        }
        catch (IOException e) { throw new ServerError("Failed unzipping dataset: " + datasetName, e); }

        try {
            Database.copy(
                new File(unzipDir, dbFullName),
                dbName,
                new DatabaseConfiguration().setDirectory(dbDir.getPath()));
        }
        catch (CouchbaseLiteException e) {
            throw new CblApiFailure("Failed copying dataset: " + datasetName + " to " + dbName, e);
        }

        openDb(dbName, ctxt);
    }

    private void openDb(@NonNull String name, @NonNull TestContext ctxt) {
        Database db = ctxt.getDb(name);
        if (db != null) { return; }

        final File dbDir = ctxt.getDbDir();
        if (dbDir == null) { throw new ServerError("Cannot find test directory for open"); }

        final DatabaseConfiguration dbConfig = new DatabaseConfiguration().setDirectory(dbDir.getPath());
        try { db = new Database(name, dbConfig); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed opening database: " + name, e); }

        ctxt.addDb(name, db);
        Log.i(TAG, "Created database: " + name);
    }

    private boolean closeDbInternal(@NonNull String name, @NonNull TestContext ctxt) {
        final Database db = ctxt.removeDb(name);
        if (db != null) {
            try {
                db.close();
                return true;
            }
            catch (CouchbaseLiteException e) {
                throw new CblApiFailure("Failed closing database: " + name, e);
            }
        }

        return false;
    }
}
