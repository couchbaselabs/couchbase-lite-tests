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
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.nanohttpd.protocols.http.response.Status;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.DatabaseConfiguration;
import com.couchbase.lite.Document;
import com.couchbase.lite.Result;
import com.couchbase.lite.ResultSet;
import com.couchbase.lite.internal.core.C4Database;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public final class DatabaseService {
    private static final String TAG = "DB_SVC";

    private static final String ZIP_EXTENSION = ".zip";
    private static final String DB_EXTENSION = C4Database.DB_EXTENSION;
    private static final String DB_DIR = "dbs/";

    // Utility methods

    @NonNull
    public static String[] parseCollectionFullName(@NonNull String collName) {
        final String[] collScopeAndName = collName.split("\\.");
        if ((collScopeAndName.length != 2)
            || StringUtils.isEmpty(collScopeAndName[0])
            || StringUtils.isEmpty(collScopeAndName[1])) {
            throw new ClientError("Cannot parse collection name: " + collName);
        }
        return collScopeAndName;
    }

    @NonNull
    public static String getDocumentFullName(@NonNull Document document) {
        final Collection collection = document.getCollection();
        return ((collection == null) ? "???" : collection.getFullName()) + "." + document.getId();
    }

    @NonNull
    public static String[] parseCollectionFQN(@NonNull String collFQN) {
        final String[] collDbScopeAndName = collFQN.split("\\.");
        if ((collDbScopeAndName.length != 3)
            || StringUtils.isEmpty(collDbScopeAndName[0])
            || StringUtils.isEmpty(collDbScopeAndName[1])
            || StringUtils.isEmpty(collDbScopeAndName[2])) {
            throw new ClientError("Cannot parse collection fqn: " + collFQN);
        }
        return collDbScopeAndName;
    }

    @NonNull
    public static String getCollectionFQN(@NonNull String[] collFQN) {
        return String.join(".", collFQN);
    }

    @NonNull
    public static String getCollectionFQN(@NonNull Collection collection) {
        return collection.getDatabase().getName() + "." + collection.getFullName();
    }

    @NonNull
    public static String getCollectionFQN(@NonNull Database db, @NonNull String collectionFullName) {
        return db.getName() + "." + collectionFullName;
    }

    @NonNull
    public static String getDocumentFQN(@NonNull Document document) {
        final Collection collection = document.getCollection();
        return ((collection == null) ? "???" : getCollectionFQN(collection)) + "." + document.getId();
    }

    @NonNull
    public static String getDocumentFQN(@NonNull Collection collection, @NonNull String docId) {
        return getCollectionFQN(collection) + "." + docId;
    }

    @NonNull
    public static String getDocumentFQN(@NonNull String dbName, @NonNull String collectionName, @NonNull String docId) {
        return dbName + "." + collectionName + "." + docId;
    }


    // Instance members

    public void init(@NonNull TestContext ctxt) {
        final String testDir = "tests_" + StringUtils.randomString(6);
        final File dbDir = new File(TestApp.getApp().getFilesDir(), testDir);
        if (!dbDir.mkdirs() || !dbDir.canWrite()) {
            throw new ServerError("Could not create db directory in init: " + dbDir);
        }
        ctxt.setDbDir(dbDir);
    }

    @NonNull
    public Database getOpenDb(@NonNull TestContext ctxt, @NonNull String dbName) {
        final Database db = ctxt.getDb(dbName);
        if (db == null) { throw new ClientError("Database not open: " + dbName); }
        return db;
    }

    public void closeDb(@NonNull TestContext ctxt, @NonNull String name) {
        if (closeDbInternal(ctxt, name)) { return; }
        Log.err(TAG, "Attempt to close a database that is not open: " + name);
    }

    @NonNull
    public Set<Collection> getCollections(
        @NonNull TestContext ctxt,
        @NonNull Database db,
        @NonNull TypedList collectionNames) {
        final Set<Collection> collections = new HashSet<>();
        for (int j = 0; j < collectionNames.size(); j++) {
            final String collectionName = collectionNames.getString(j);
            if (collectionName == null) { throw new ClientError("Empty collection name (" + j + ")"); }
            collections.add(getCollection(ctxt, db, collectionName));
        }
        return collections;
    }

    @NonNull
    public Collection getCollection(@NonNull TestContext ctxt, @NonNull Database db, @NonNull String collName) {
        Collection collection = ctxt.getOpenCollection(getCollectionFQN(db, collName));
        if (collection != null) { return collection; }

        final String[] collScopeAndName = parseCollectionFullName(collName);
        try { collection = db.getCollection(collScopeAndName[1], collScopeAndName[0]); }
        catch (CouchbaseLiteException e) {
            throw new CblApiFailure("Failed retrieving collection: " + collName + " from db " + db.getName(), e);
        }
        if (collection == null) {
            throw new ClientError("Database " + db.getName() + " does not contain collection " + collName);
        }

        ctxt.addOpenCollection(collection);

        return collection;
    }

    @NonNull
    public Map<String, Object> getDocument(
        @NonNull TestContext ctxt,
        @NonNull String dbName,
        @NonNull String collName,
        @NonNull String docId) {
        final Document doc = getDocOrNull(ctxt, getOpenDb(ctxt, dbName), collName, docId);
        if (doc == null) {
            throw new ClientError(Status.NOT_FOUND, "Document not found: " + getDocumentFQN(dbName, collName, docId));
        }
        return doc.toMap();
    }

    @NonNull
    public Document getDocument(@NonNull Collection collection, @NonNull String docId) {
        final Document doc = getDocOrNull(collection, docId);
        if (doc == null) {
            throw new ClientError(Status.NOT_FOUND, "Document not found: " + getDocumentFQN(collection, docId));
        }
        return doc;
    }

    @Nullable
    public Document getDocOrNull(
        @NonNull TestContext ctxt,
        @NonNull Database db,
        @NonNull String collName,
        @NonNull String docId) {
        return getDocOrNull(getCollection(ctxt, db, collName), docId);
    }

    @Nullable
    public Document getDocOrNull(@NonNull Collection collection, @NonNull String docId) {
        try { return collection.getDocument(docId); }
        catch (CouchbaseLiteException e) {
            throw new CblApiFailure("Failed getting doc " + docId + " from collection " + collection, e);
        }
    }

    public String runQuery(@NonNull Database db, @NonNull String query) {
        final StringBuilder json = new StringBuilder("[");
        try (ResultSet rs = db.createQuery(query).execute()) {
            for (Result r: rs.allResults()) {
                if (json.length() > 1) { json.append(","); }
                json.append(r.toJSON());
            }
        }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Query failed: \"" + query + "\"", e); }

        return json.append("]").toString();
    }

    // New stream constructors are supported only in API 26+
    public void installDatabase(@NonNull TestContext ctxt, @NonNull String dbName, List<String[]> collFQNs) {
        final File dbDir = ctxt.getDbDir();
        if (dbDir == null) { throw new ServerError("Cannot find test directory on install dataset"); }

        if (Database.exists(dbName, dbDir)) { throw new ClientError("Database already exists: " + dbName); }

        final Database db = openDb(ctxt, dbName);
        for (String[] fqn: collFQNs) {
            try { db.createCollection(fqn[1], fqn[0]); }
            catch (CouchbaseLiteException e) {
                throw new CblApiFailure("Failed creating collection: " + getCollectionFQN(fqn), e);
            }
        }

        ctxt.addDb(dbName, db);
    }

    // New stream constructors are supported only in API 26+
    public void installDataset(@NonNull TestContext ctxt, @NonNull String datasetName, @NonNull String dbName) {
        final File dbDir = ctxt.getDbDir();
        if (dbDir == null) { throw new ServerError("Cannot find test directory on install dataset"); }

        if (Database.exists(datasetName, dbDir)) { throw new ClientError("Database already exists: " + dbName); }

        final FileUtils fileUtils = new FileUtils();

        final File unzipDir = new File(dbDir, "tmp");
        if (unzipDir.exists() && !fileUtils.deleteRecursive(unzipDir)) {
            throw new ServerError("Failed deleting unzip tmp directory");
        }
        if (!unzipDir.mkdirs()) { throw new ServerError("Failed creating unzip tmp directory"); }

        final String dbFullName = datasetName + DB_EXTENSION;
        try (InputStream in = TestApp.getApp().getAsset(DB_DIR + dbFullName + ZIP_EXTENSION)) {
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

        openDb(ctxt, dbName);
    }

    @NonNull
    private Database openDb(@NonNull TestContext ctxt, @NonNull String name) {
        Database db = ctxt.getDb(name);
        if (db != null) { return db; }

        final File dbDir = ctxt.getDbDir();
        if (dbDir == null) { throw new ServerError("Cannot find test directory for open"); }

        final DatabaseConfiguration dbConfig = new DatabaseConfiguration().setDirectory(dbDir.getPath());
        try { db = new Database(name, dbConfig); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed opening database: " + name, e); }

        ctxt.addDb(name, db);
        Log.p(TAG, "Created database: " + name);

        return db;
    }

    private boolean closeDbInternal(@NonNull TestContext ctxt, @NonNull String name) {
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
