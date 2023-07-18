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
package com.couchbase.lite.mobiletest.tests;

import androidx.annotation.NonNull;

import java.io.File;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.HashMap;
import java.util.Locale;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.DatabaseConfiguration;
import com.couchbase.lite.internal.core.C4Database;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestException;
import com.couchbase.lite.mobiletest.TypedMap;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.Log;


public final class DatabaseManager {
    private static final String TAG = "DBMGR";

    private static final String SYM_OPEN_DBS = "~OPEN_DBS";

    private static final String DB_EXTENSION = C4Database.DB_EXTENSION;


    private final File dbRoot;

    public DatabaseManager() {
        final String testDir = "tests_"
            + new SimpleDateFormat("MM_dd_HH_mm_ss", Locale.getDefault()).format(new Date());
        dbRoot = new File(TestApp.getApp().getFilesDir(), testDir);
        if (!dbRoot.mkdirs() || !dbRoot.canWrite()) {
            throw new IllegalStateException("Could not create directory: " + dbRoot);
        }
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @NonNull
    public Database openDb(@NonNull String name, @NonNull Memory memory) throws TestException {
        TypedMap openDbs = memory.getMap(SYM_OPEN_DBS);
        if (openDbs != null) {
            final Database db = openDbs.get(name, Database.class);
            if (db != null) { return db; }
        }
        else {
            memory.put(SYM_OPEN_DBS, new HashMap<>());
            // openDbs cannot be null
            openDbs = memory.getMap(SYM_OPEN_DBS);
        }

        final Database db;
        final DatabaseConfiguration dbConfig = new DatabaseConfiguration().setDirectory(dbRoot.getPath());
        try { db = new Database(name, dbConfig); }
        catch (CouchbaseLiteException e) {
            throw new IllegalStateException("Failed opening database: " + name, e);
        }

        openDbs.put(name, db);
        Log.i(TAG, "Created database: " + name);

        return db;
    }

    public void closeDb(@NonNull String name, @NonNull Memory memory) throws TestException {
        if (closeDbInternal(name, memory)) { return; }
        Log.w(TAG, "Attempt to close a database that is not open: " + name);
    }


    // New stream constructors are supported only in API 26+
    @SuppressWarnings("IOStreamConstructor")
    @NonNull
    public Database installDb(@NonNull String datasetName, @NonNull String dbName, @NonNull Memory memory)
        throws TestException {
        closeDbInternal(dbName, memory);

        final File tmpDir = new File("tmpDir");

        if (!new File(tmpDir, datasetName + DB_EXTENSION).exists()) {
            try (InputStream in = new FileInputStream(datasetName)) { new FileUtils().unzip(in, tmpDir); }
            catch (IOException e) { throw new IllegalStateException("Faild unzipping dataset: " + datasetName, e); }
        }

        try { Database.copy(new File(tmpDir, datasetName + DB_EXTENSION), dbName, new DatabaseConfiguration()); }
        catch (CouchbaseLiteException e) {
            throw new IllegalStateException("Failed copying dataset: " + datasetName + " to " + dbName, e);
        }

        return openDb(dbName, memory);
    }

    // !!! The req may contain a spec for datasets to be loaded
    public void reset(@NonNull Map<String, Object> req, @NonNull Memory memory) {
        final TypedMap openDbs = memory.getMap(SYM_OPEN_DBS);
        if ((openDbs == null) || openDbs.isEmpty()) { return; }

        for (String key: openDbs.getKeys()) {
            final Database db = openDbs.get(key, Database.class);
            if (db == null) {
                Log.e(TAG, "Attempt to close non-existent database: " + key);
                continue;
            }

            try { db.delete(); }
            catch (CouchbaseLiteException e) { Log.w(TAG, "Failed deleting database: " + db.getName()); }
        }
    }

    private boolean closeDbInternal(@NonNull String name, @NonNull Memory memory) throws TestException {
        final TypedMap openDbs = memory.getMap(SYM_OPEN_DBS);
        if (openDbs != null) {
            final Database db = openDbs.remove(name, Database.class);
            if (db != null) {
                try {
                    db.close();
                    return true;
                }
                catch (CouchbaseLiteException e) {
                    throw new IllegalStateException("Failed closing database: " + name, e);
                }
            }
        }

        return false;
    }
}
