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
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.DatabaseConfiguration;
import com.couchbase.lite.Document;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.internal.core.C4Database;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.data.TypedList;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.tools.CollectionDocsBuilder;
import com.couchbase.lite.mobiletest.tools.CollectionsBuilder;
import com.couchbase.lite.mobiletest.tools.DocPruner;
import com.couchbase.lite.mobiletest.tools.DocUpdater;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public final class DatabaseService {
    private static final String TAG = "DB_SVC";

    private static final String SYM_OPEN_DBS = "~OPEN_DBS";
    private static final String SYM_DB_DIR = "~DB_DIR";

    private static final String ZIP_EXTENSION = ".zip";
    private static final String DB_EXTENSION = C4Database.DB_EXTENSION;

    private static final String KEY_DATASETS = "datasets";
    private static final String KEY_DATABASE = "database";
    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_UPDATES = "updates";
    private static final String KEY_TYPE = "type";
    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_DOC_ID = "documentID";
    private static final String KEY_UPDATE_PROPS = "updatedProperties";
    private static final String KEY_REMOVED_PROPS = "removedProperties";

    private static final List<String> LEGAL_COLLECTION_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_DATABASE);
        l.add(KEY_COLLECTIONS);
        LEGAL_COLLECTION_KEYS = Collections.unmodifiableList(l);
    }

    private static final List<String> LEGAL_DATASET_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_DATASETS);
        LEGAL_DATASET_KEYS = Collections.unmodifiableList(l);
    }

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
    // Instance methods


    public void reset(@NonNull Memory mem) {
        final File dbDir = mem.remove(SYM_DB_DIR, File.class);
        if (dbDir == null) { return; }

        final Map<?, ?> dbs = mem.remove(SYM_OPEN_DBS, Map.class);
        if ((dbs == null) || dbs.isEmpty()) { return; }
        final TypedMap openDbs = new TypedMap(dbs);

        for (String key: openDbs.getKeys()) {
            final Database db = openDbs.get(key, Database.class);
            if (db == null) {
                Log.w(TAG, "Attempt to close non-existent database: " + key);
                continue;
            }

            final String dbName = db.getName();
            try { db.close(); }
            catch (CouchbaseLiteException e) {
                throw new CblApiFailure("Failed closing database: " + dbName + " in " + dbDir, e);
            }
        }

        if (!new FileUtils().deleteRecursive(dbDir)) { Log.w(TAG, "failed deleting db dir on reset: " + dbDir); }
    }

    public void init(TypedMap req, Memory mem) {
        final TestApp app = TestApp.getApp();

        final String testDir = "tests_" + StringUtils.randomString(6);
        final File dbDir = new File(app.getFilesDir(), testDir);
        if (!dbDir.mkdirs() || !dbDir.canWrite()) {
            throw new ServerError("Could not create db dir on init: " + dbDir);
        }
        mem.put(SYM_DB_DIR, dbDir);

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
                installDataset(dataset, dbName, mem);
            }
        }
    }

    @NonNull
    public Database getOpenDb(@NonNull String name, @NonNull Memory mem) {
        final TypedMap openDbs = mem.getMap(SYM_OPEN_DBS);
        if (openDbs == null) { throw new ClientError("There are no open databases"); }
        final Database db = openDbs.get(name, Database.class);
        if (db == null) { throw new ClientError("Database not open: " + name); }
        return db;
    }

    public void closeDb(@NonNull String name, @NonNull Memory mem) {
        if (closeDbInternal(name, mem)) { return; }
        Log.w(TAG, "Attempt to close a database that is not open: " + name);
    }

    @Nullable
    public Collection getCollection(@NonNull Database db, @NonNull String collectionFullName) {
        final String[] collName = collectionFullName.split("\\.");
        if ((collName.length != 2) || collName[0].isEmpty() || collName[1].isEmpty()) {
            throw new ClientError("Cannot parse collection name: " + collectionFullName);
        }

        try { return db.getCollection(collName[1], collName[0]); }
        catch (CouchbaseLiteException e) {
            throw new CblApiFailure("Failed retrieving collection: " + collectionFullName, e);
        }
    }

    @NonNull
    public Map<String, Object> getAllDocsV1(@NonNull TypedMap req, @NonNull Memory mem) {
        req.validate(LEGAL_COLLECTION_KEYS);
        return new CollectionDocsBuilder(
            new CollectionsBuilder(req.getList(KEY_COLLECTIONS), getNamedDb(req, mem)).build())
            .build();
    }

    @NonNull
    public Map<String, Object> updateDbV1(@NonNull TypedMap req, @NonNull Memory mem) {
        req.validate(LEGAL_UPDATES_KEYS);

        final TypedList updates = req.getList(KEY_UPDATES);
        if (updates == null) { throw new ClientError("Database update request has no updates"); }

        final Database db = getNamedDb(req, mem);
        final int n = updates.size();
        for (int i = 0; i < n; i++) {
            final TypedMap update = updates.getMap(i);
            if (update == null) { throw new ServerError("Null update request"); }
            update.validate(LEGAL_UPDATE_KEYS);

            final String collectionName = update.getString(KEY_COLLECTION);
            if (collectionName == null) { throw new ClientError("Database update request is missing collection name"); }

            final Collection collection = getCollection(db, collectionName);
            if (collection == null) { throw new ClientError("Database update request is missing a document id"); }

            final String id = update.getString(KEY_DOC_ID);
            if (id == null) { throw new ClientError("Database update request is missing a document id"); }

            final Document doc;
            try { doc = collection.getDocument(id); }
            catch (CouchbaseLiteException e) {
                throw new CblApiFailure("Failed retrieving document: " + id + " from collection " + collectionName, e);
            }
            if (doc == null) {
                throw new ServerError("Failed retrieving document: " + id + " from collection " + collectionName);
            }

            MutableDocument mDoc = doc.toMutable();
            final TypedList changes = update.getList(KEY_UPDATE_PROPS);
            if (changes != null) { mDoc = new DocUpdater(mDoc).update(changes); }

            final TypedList deletions = update.getList(KEY_REMOVED_PROPS);
            if (deletions != null) { mDoc = new DocPruner(mDoc).prune(deletions); }

            try { collection.save(mDoc); }
            catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed saving updated document", e); }
        }
        return Collections.emptyMap();
    }

    // New stream constructors are supported only in API 26+
    @SuppressWarnings("ConstantConditions")
    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    private void installDataset(@NonNull String datasetName, @NonNull String dbName, @NonNull Memory mem) {
        final File dbDir = mem.get(SYM_DB_DIR, File.class);
        if (dbDir == null) { throw new ServerError("Cannot find test directory on install dataset"); }

        final String dbFullName = datasetName + DB_EXTENSION;
        if (new File(dbDir, dbFullName).exists()) { throw new ClientError("Database already exists: " + dbName); }

        final FileUtils fileUtils = new FileUtils();

        final File unzipDir = new File(dbDir, "tmp");
        if (unzipDir.exists() && !fileUtils.deleteRecursive(unzipDir)) {
            throw new ServerError("Failed deleting unzip tmp directory");
        }
        if (!unzipDir.mkdirs()) { throw new ServerError("Failed creating unzip tmp directory"); }

        try (InputStream in = TestApp.getApp().getAsset(dbFullName + ZIP_EXTENSION)) { fileUtils.unzip(in, unzipDir); }
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

        openDb(dbName, mem);
    }

    @SuppressWarnings("ConstantConditions")
    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    private void openDb(@NonNull String name, @NonNull Memory mem) {
        TypedMap openDbs = mem.getMap(SYM_OPEN_DBS);
        if ((openDbs != null) && (openDbs.get(name, Database.class) != null)) { return; }

        mem.put(SYM_OPEN_DBS, new HashMap<>());
        openDbs = mem.getMap(SYM_OPEN_DBS);

        final File dbDir = mem.get(SYM_DB_DIR, File.class);
        if (dbDir == null) { throw new ServerError("Cannot find test directory for open"); }

        final Database db;
        final DatabaseConfiguration dbConfig = new DatabaseConfiguration().setDirectory(dbDir.getPath());
        try { db = new Database(name, dbConfig); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed opening database: " + name, e); }

        openDbs.put(name, db);
        Log.i(TAG, "Created database: " + name);
    }

    private boolean closeDbInternal(@NonNull String name, @NonNull Memory mem) {
        final TypedMap openDbs = mem.getMap(SYM_OPEN_DBS);
        if (openDbs != null) {
            final Database db = openDbs.remove(name, Database.class);
            if (db != null) {
                try {
                    db.close();
                    return true;
                }
                catch (CouchbaseLiteException e) {
                    throw new CblApiFailure("Failed closing database: " + name, e);
                }
            }
        }

        return false;
    }

    @NonNull
    private Database getNamedDb(@NonNull TypedMap req, @NonNull Memory mem) {
        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("All Docs request doesn't specify a database"); }
        return getOpenDb(dbName, mem);
    }
}
