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

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.HashMap;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.DatabaseConfiguration;
import com.couchbase.lite.internal.core.C4Database;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.data.TypedList;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
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

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @NonNull
    public Database openDb(@NonNull String name, @NonNull Memory mem) {
        TypedMap openDbs = mem.getMap(SYM_OPEN_DBS);
        if (openDbs != null) {
            final Database db = openDbs.get(name, Database.class);
            if (db != null) { return db; }
        }
        else {
            mem.put(SYM_OPEN_DBS, new HashMap<>());
            // openDbs cannot be null
            openDbs = mem.getMap(SYM_OPEN_DBS);
        }

        final File dbDir = mem.get(SYM_DB_DIR, File.class);
        if (dbDir == null) { throw new ServerError("Cannot find test directory for open"); }

        final Database db;
        final DatabaseConfiguration dbConfig = new DatabaseConfiguration().setDirectory(dbDir.getPath());
        try { db = new Database(name, dbConfig); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed opening database: " + name, e); }

        openDbs.put(name, db);
        Log.i(TAG, "Created database: " + name);

        return db;
    }

    public void closeDb(@NonNull String name, @NonNull Memory mem) {
        if (closeDbInternal(name, mem)) { return; }
        Log.w(TAG, "Attempt to close a database that is not open: " + name);
    }

    public void reset(@NonNull TypedMap req, @NonNull Memory mem) {
        final File dbDir = mem.remove(SYM_DB_DIR, File.class);
        if (dbDir == null) { throw new ServerError("Cannot find test directory for reset"); }

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

        final TypedMap datasets = req.getMap(KEY_DATASETS);
        if (datasets == null) { throw new ClientError("Missing dataset specification in init"); }
        for (String dataset: datasets.getKeys()) {
            final TypedList databases = req.getList(dataset);
            if (databases == null) { throw new ClientError("Missing target databases in dataset spec in init"); }
            for (int i = 0; i < databases.size(); i++) {
                final String dbName = databases.getString(i);
                if (dbName == null) { throw new ClientError("Empty target databases in dataset spec in init"); }
                installDataset(dataset, dbName, mem);
            }
        }
    }

    // New stream constructors are supported only in API 26+
    @SuppressWarnings("IOStreamConstructor")
    private void installDataset(@NonNull String datasetName, @NonNull String dbName, @NonNull Memory mem) {
        final File dbDir = mem.remove(SYM_DB_DIR, File.class);
        if (dbDir == null) { throw new ServerError("Cannot find test directory on install dataset"); }

        final String dbFullName = datasetName + DB_EXTENSION;
        if (new File(dbDir, dbFullName).exists()) { throw new ClientError("Database already exists: " + dbName); }

        final FileUtils fileUtils = new FileUtils();

        final File unzipDir = new File(dbDir, "tmp");
        if (unzipDir.exists() && !fileUtils.deleteRecursive(unzipDir)) {
            throw new ServerError("Failed deleting unzip tmp directory");
        }
        if (!unzipDir.mkdirs()) { throw new ServerError("Failed creating unzip tmp directory"); }

        try (InputStream in = new FileInputStream(dbFullName + ZIP_EXTENSION)) { fileUtils.unzip(in, unzipDir); }
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
}
