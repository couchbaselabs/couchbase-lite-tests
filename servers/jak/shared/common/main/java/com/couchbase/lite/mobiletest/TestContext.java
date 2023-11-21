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
import com.couchbase.lite.mobiletest.changes.Snapshot;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.DocReplListener;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.Log;


public final class TestContext {
    private static final String TAG = "CONTEXT";

    @NonNull
    public static TestContext validateContext(@Nullable TestContext ctxt) {
        if (ctxt == null) { throw new ClientError("No context for test"); }
        return ctxt;
    }

    @NonNull
    private final String client;
    @NonNull
    private final String name;
    @Nullable
    private File dbDir;
    @Nullable
    private Map<String, Database> openDbs;
    @Nullable
    private Map<String, Collection> openCollections;
    @Nullable
    private Map<String, Replicator> openRepls;
    @Nullable
    private Map<String, DocReplListener> openListeners;
    @Nullable
    private Map<String, Snapshot> openSnapshots;

    TestContext(@NonNull String client, @NonNull String name) {
        this.client = client;
        this.name = name;
    }

    public void close() {
        // belt
        openListeners = null;

        // ... and suspenders...
        openSnapshots = null;

        stopRepls();

        closeCollections();

        deleteDbs();
    }

    @NonNull
    public String getClient() { return client; }

    @NonNull
    public String getName() { return name; }

    public void setDbDir(@NonNull File dbDir) {
        if (this.dbDir != null) { throw new ServerError("Attempt to replace the db dir"); }
        this.dbDir = dbDir;
    }

    @Nullable
    public File getDbDir() { return dbDir; }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH")
    public void addDb(@NonNull String name, @NonNull Database db) {
        if (openDbs == null) { openDbs = new HashMap<>(); }
        if (openDbs.containsKey(name)) { throw new ClientError("Attempt to replace an open database"); }
        openDbs.put(name, db);
    }

    @Nullable
    public Database getDb(@NonNull String name) { return (openDbs == null) ? null : openDbs.get(name); }

    @Nullable
    public Database removeDb(@NonNull String name) { return (openDbs == null) ? null : openDbs.remove(name); }

    @Nullable
    public Collection getOpenCollection(@NonNull String collFqn) {
        return (openCollections == null) ? null : openCollections.get(collFqn);
    }

    public void addOpenCollection(@NonNull Collection collection) {
        if (openCollections == null) { openCollections = new HashMap<>(); }
        openCollections.put(DatabaseService.getCollectionFQN(collection), collection);
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH")
    public void addRepl(@NonNull String id, @NonNull Replicator repl) {
        if (openRepls == null) { openRepls = new HashMap<>(); }
        if (openRepls.containsKey(id)) { throw new ClientError("Attempt to replace an existing replicator"); }
        openRepls.put(id, repl);
    }

    @Nullable
    public Replicator getRepl(@NonNull String name) { return (openRepls == null) ? null : openRepls.get(name); }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH")
    public void addDocReplListener(@NonNull String replId, @NonNull DocReplListener listener) {
        if (openListeners == null) { openListeners = new HashMap<>(); }
        if (openListeners.containsKey(replId)) { throw new ClientError("Attempt to replace an existing doc listener"); }
        openListeners.put(replId, listener);
    }

    @Nullable
    public DocReplListener getDocReplListener(@NonNull String id) {
        return (openListeners == null) ? null : openListeners.get(id);
    }

    @NonNull
    public String addSnapshot(@NonNull Snapshot snapshot) {
        final String snapshotId = UUID.randomUUID().toString();
        if (openSnapshots == null) { openSnapshots = new HashMap<>(); }
        openSnapshots.put(snapshotId, snapshot);
        return snapshotId;
    }

    @NonNull
    public Snapshot getSnapshot(@NonNull String id) {
        if (openSnapshots != null) {
            final Snapshot snapshot = openSnapshots.get(id);
            if (snapshot != null) { return snapshot; }
        }
        throw new ClientError("No such snapshot: " + id);
    }

    private void stopRepls() {
        final Map<String, Replicator> liveRepls = this.openRepls;
        this.openRepls = null;
        if (liveRepls == null) { return; }
        for (Replicator repl: liveRepls.values()) {
            if (repl != null) { repl.stop(); }
        }
    }

    private void closeCollections() {
        final Map<String, Collection> openColls = openCollections;
        this.openCollections = null;
        if (openColls == null) { return; }
        for (Collection collection: openColls.values()) { collection.close(); }
    }

    private void deleteDbs() {
        final File dbDir = this.dbDir;
        this.dbDir = null;

        final Map<String, Database> openDbs = this.openDbs;
        this.openDbs = null;

        if (openDbs != null) {
            for (Map.Entry<String, Database> entry: openDbs.entrySet()) {
                final Database db = entry.getValue();
                if (db == null) {
                    Log.w(TAG, "Attempt to close non-existent database: " + entry.getKey());
                    continue;
                }

                final String dbName = db.getName();
                try { db.close(); }
                catch (CouchbaseLiteException e) {
                    throw new CblApiFailure("Failed closing database: " + dbName + " in " + dbDir, e);
                }
            }
        }

        if ((dbDir != null) && !new FileUtils().deleteRecursive(dbDir)) {
            Log.w(TAG, "Failed deleting db dir on reset: " + dbDir);
        }
    }
}
