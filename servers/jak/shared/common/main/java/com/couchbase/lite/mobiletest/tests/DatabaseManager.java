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
import java.util.List;
import java.util.Locale;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.DatabaseConfiguration;
import com.couchbase.lite.internal.core.C4Database;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestException;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.Log;


public final class DatabaseManager {
    private static final String TAG = "DBMGR";

    private static final String SYM_OPEN_DBS = "~OPEN_DBS";

    private static final String DB_EXTENSION = C4Database.DB_EXTENSION;


    private final File dbRoot;

    public DatabaseManager() {
        dbRoot = new File("tests_" + new SimpleDateFormat("MM_dd_HH_mm_ss", Locale.getDefault()).format(new Date()));
        if (!dbRoot.mkdirs() || !dbRoot.canWrite()) {
            throw new IllegalStateException("Could not create directory: " + dbRoot);
        }
    }

    @NonNull
    public Database createDb(@NonNull String name, @NonNull Memory memory) throws TestException {
        final Database db;
        final DatabaseConfiguration dbConfig = new DatabaseConfiguration().setDirectory(dbRoot.getPath());
        try { db = new Database(name, dbConfig); }
        catch (CouchbaseLiteException e) {
            throw new TestException(TestException.TESTSERVER, 0, "Failed opening database: " + name, e);
        }
        memory.addToList(SYM_OPEN_DBS, db);
        return db;
    }

    // New stream constructors are supported only in API 26+
    @SuppressWarnings("IOStreamConstructor")
    @NonNull
    public Database installDb(@NonNull String datasetName, @NonNull String dbName, @NonNull Memory memory)
        throws TestException {
        final File tmpDir = new File("tmpDir");

        if (!new File(tmpDir, datasetName + DB_EXTENSION).exists()) {
            try (InputStream in = new FileInputStream(datasetName)) { new FileUtils().unzip(in, tmpDir); }
            catch (IOException e) {
                throw new IllegalStateException("?????", e);
            }
        }

        try { Database.copy(new File(tmpDir, datasetName + DB_EXTENSION), dbName, new DatabaseConfiguration()); }
        catch (CouchbaseLiteException e) {
            throw new TestException(
                TestException.TESTSERVER,
                0,
                "Failed copying dataset: " + datasetName + " to " + dbName,
                e);
        }

        return createDb(dbName, memory);
    }

    public void reset(@NonNull Memory memory) {
        final List<Object> dbs = memory.getList(SYM_OPEN_DBS);
        if (dbs == null) { return; }

        for (Object obj: dbs) {
            if (!(obj instanceof Database)) {
                Log.e(TAG, "Attempt to close non-database: " + obj);
                continue;
            }

            final Database db = (Database) obj;
            try { db.delete(); }
            catch (CouchbaseLiteException e) {
                Log.w(TAG, "Failed deleting database: " + db.getName());
            }
        }
    }
}
