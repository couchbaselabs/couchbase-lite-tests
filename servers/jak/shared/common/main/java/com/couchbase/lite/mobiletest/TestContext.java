package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.util.HashMap;
import java.util.Map;
import java.util.UUID;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.URLEndpointListener;
import com.couchbase.lite.mobiletest.changes.Snapshot;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.DocReplListener;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.util.FileUtils;


public final class TestContext implements AutoCloseable {
    private static final String TAG = "CONTEXT";

    private static final String DEFAULT_DATASET_VERSION = "3.2";


    @NonNull
    private final String client;
    @NonNull
    private final String datasetVersion;
    @Nullable
    private String testName;
    @Nullable
    private File dbDir;
    @Nullable
    private Map<String, Database> openDbs;
    @Nullable
    private Map<String, Collection> openCollections;
    @Nullable
    private Map<String, Replicator> openRepls;
    @Nullable
    private Map<String, DocReplListener> openDocListeners;
    @Nullable
    private Map<String, Snapshot> openSnapshots;
    @Nullable
    private Map<String, URLEndpointListener> openEndptListeners;

    TestContext(@NonNull String client, @Nullable String datasetVersion) {
        this.client = client;
        // !!! Unimplemented: this is completely ignored
        this.datasetVersion = (datasetVersion == null) ? DEFAULT_DATASET_VERSION : datasetVersion;
    }

    @Override
    public void close() {
        // belt
        openDocListeners = null;

        // ... and suspenders...
        openSnapshots = null;

        stopRepls();

        stopEndptListeners();

        closeCollections();

        deleteDbs();
    }

    @NonNull
    public String getClient() { return client; }

    @NonNull
    public String getDatasetVersion() { return datasetVersion; }

    public void setTestName(@Nullable String testName) { this.testName = testName; }

    @Nullable
    public String getTestName() { return testName; }


    public void setDbDir(@NonNull File dbDir) {
        if (this.dbDir != null) { throw new ServerError("Attempt to replace the db dir"); }
        this.dbDir = dbDir;
    }

    @Nullable
    public File getDbDir() { return dbDir; }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH")
    public void addDb(@NonNull String name, @NonNull Database db) {
        Log.p(TAG, "Adding database to context: " + name);
        Map<String, Database> dbs = openDbs;
        if (dbs == null) {
            dbs = new HashMap<>();
            openDbs = dbs;
        }
        if (dbs.containsKey(name)) { throw new ClientError("Attempt to replace an open database"); }
        dbs.put(name, db);
    }

    @Nullable
    public Database getDb(@NonNull String name) {
        final Map<String, Database> dbs = openDbs;
        return (dbs == null) ? null : dbs.get(name);
    }

    @Nullable
    public Database removeDb(@NonNull String name) {
        final Map<String, Database> dbs = openDbs;
        return (dbs == null) ? null : dbs.remove(name);
    }

    @Nullable
    public Collection getOpenCollection(@NonNull String collFqn) {
        final Map<String, Collection> collections = openCollections;
        return (collections == null) ? null : collections.get(collFqn);
    }

    public void addOpenCollection(@NonNull Collection collection) {
        Map<String, Collection> collections = openCollections;
        if (collections == null) {
            collections = new HashMap<>();
            openCollections = collections;
        }
        collections.put(DatabaseService.getCollectionFQN(collection), collection);
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH")
    public void addRepl(@NonNull String id, @NonNull Replicator repl) {
        Map<String, Replicator> repls = openRepls;
        if (repls == null) {
            repls = new HashMap<>();
            openRepls = repls;
        }
        if (repls.containsKey(id)) { throw new ClientError("Attempt to replace an existing replicator"); }
        repls.put(id, repl);
    }

    @Nullable
    public Replicator getRepl(@NonNull String name) {
        final Map<String, Replicator> repls = openRepls;
        return (repls == null) ? null : repls.get(name);
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH")
    public void addDocReplListener(@NonNull String replId, @NonNull DocReplListener listener) {
        Map<String, DocReplListener> docListeners = openDocListeners;
        if (openDocListeners == null) {
            docListeners = new HashMap<>();
            openDocListeners = docListeners;
        }
        if (docListeners.containsKey(replId)) { throw new ClientError("Attempt to replace an existing doc listener"); }
        docListeners.put(replId, listener);
    }

    @Nullable
    public DocReplListener getDocReplListener(@NonNull String id) {
        final Map<String, DocReplListener> docListeners = openDocListeners;
        return (docListeners == null) ? null : docListeners.get(id);
    }

    @NonNull
    public String addSnapshot(@NonNull Snapshot snapshot) {
        final String snapshotId = UUID.randomUUID().toString();
        Map<String, Snapshot> snapshots = openSnapshots;
        if (openSnapshots == null) {
            snapshots = new HashMap<>();
            openSnapshots = snapshots;
        }
        snapshots.put(snapshotId, snapshot);
        return snapshotId;
    }

    @NonNull
    public Snapshot getSnapshot(@NonNull String id) {
        final Map<String, Snapshot> shapshots = openSnapshots;
        if (shapshots != null) {
            final Snapshot snapshot = shapshots.get(id);
            if (snapshot != null) { return snapshot; }
        }
        throw new ClientError("No such snapshot: " + id);
    }

    public void addEndptListener(@NonNull String id, @NonNull URLEndpointListener listener) {
        Map<String, URLEndpointListener> endptListeners = openEndptListeners;
        if (endptListeners == null) {
            endptListeners = new HashMap<>();
            openEndptListeners = endptListeners;
        }
        if (endptListeners.containsKey(id)) { throw new ClientError("Attempt to replace an existing listener"); }
        endptListeners.put(id, listener);
    }

    @Nullable
    public URLEndpointListener getEndptListener(@NonNull String id) {
        final Map<String, URLEndpointListener> endptListeners = openEndptListeners;
        return (endptListeners == null) ? null : endptListeners.get(id);
    }

    private void stopRepls() {
        final Map<String, Replicator> liveRepls = openRepls;
        openRepls = null;
        if (liveRepls == null) { return; }
        for (Replicator repl: liveRepls.values()) {
            if (repl != null) { repl.stop(); }
        }
    }

    private void stopEndptListeners() {
        final Map<String, URLEndpointListener> liveEndptListeners = openEndptListeners;
        openEndptListeners = null;
        if (liveEndptListeners == null) { return; }
        for (URLEndpointListener listener: liveEndptListeners.values()) {
            if (listener != null) { listener.stop(); }
        }
    }

    private void closeCollections() {
        final Map<String, Collection> liveCollections = openCollections;
        openCollections = null;
        if (liveCollections == null) { return; }
        for (Collection collection: liveCollections.values()) { collection.close(); }
    }

    private void deleteDbs() {
        final File liveDbDir = dbDir;
        dbDir = null;

        final Map<String, Database> liveDbs = openDbs;
        openDbs = null;

        if (liveDbs != null) {
            for (Map.Entry<String, Database> entry: liveDbs.entrySet()) {
                final Database db = entry.getValue();
                if (db == null) {
                    Log.err(TAG, "Attempt to close non-existent database: " + entry.getKey());
                    continue;
                }

                final String dbName = db.getName();
                try { db.close(); }
                catch (CouchbaseLiteException e) {
                    throw new CblApiFailure("Failed closing database: " + dbName + " in " + liveDbDir, e);
                }
            }
        }

        if ((liveDbDir != null) && !new FileUtils().deleteRecursive(liveDbDir)) {
            Log.err(TAG, "Failed deleting db dir on reset: " + liveDbDir);
        }
    }
}
