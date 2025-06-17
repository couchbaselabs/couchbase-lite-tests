package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.File;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.Collection;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.URLEndpointListener;
import com.couchbase.lite.mobiletest.changes.Snapshot;
import com.couchbase.lite.mobiletest.endpoints.v1.Session;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.DocReplListener;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.FileUtils;
import com.couchbase.lite.mobiletest.util.StringUtils;


@SuppressWarnings("PMD.CyclomaticComplexity")
public final class TestContext {
    private static final String TAG = "CONTEXT";

    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_DATASET = "dataset";

    private static final Set<String> LEGAL_DATABASE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_COLLECTIONS);
        l.add(KEY_DATASET);
        LEGAL_DATABASE_KEYS = Collections.unmodifiableSet(l);
    }

    @NonNull
    private final Session session;
    @NonNull
    private final String testName;
    @NonNull
    private final File dbDir;

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

    public TestContext(@NonNull TestApp app, @NonNull Session session, @NonNull String testName) {
        this.session = session;
        this.testName = testName;

        final File dbDir = new File(session.getRootDir(), "dbs");
        if (!dbDir.mkdirs()) { throw new ServerError("Failed creating test db directory: " + dbDir); }
        this.dbDir = dbDir;

        app.getDbSvc().init(this);
        app.getReplSvc().init(this);
        app.getListenerService().init(this);

        Log.p(TAG, ">>>>> START TEST: " + testName);
    }

    @NonNull
    public Session getSession() { return session; }

    @NonNull
    public String getTestName() { return testName; }

    @NonNull
    public File getDbDir() { return dbDir; }

    public void close(@NonNull TestApp app) {
        Log.p(TAG, "<<<<< END TEST: " + testName);

        // belt
        openDocListeners = null;

        // ... and suspenders...
        openSnapshots = null;

        stopRepls();

        stopEndptListeners();

        closeCollections();

        deleteDbs();

        app.clearReplSvc();
        app.clearListenerService();
        app.clearDbSvc();
    }

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

    public void createDbs(@NonNull DatabaseService dbSvc, @Nullable TypedMap databases) {
        if ((databases == null) || databases.isEmpty()) { return; }

        final Set<String> dbNames = databases.getKeys();
        for (String dbName: dbNames) {
            final TypedMap dbDesc = databases.getMap(dbName);

            if ((dbDesc == null) || dbDesc.isEmpty()) {
                createDb(this, dbSvc, dbName, null);
                continue;
            }

            dbDesc.validate(LEGAL_DATABASE_KEYS);

            final String dataset = dbDesc.getString(KEY_DATASET);
            if (dataset != null) {
                if (dbDesc.containsKey(KEY_COLLECTIONS)) {
                    throw new ClientError(
                        "Both collections and dataset specified for database " + dbName + " in reset");
                }

                if (StringUtils.isEmpty(dataset)) {
                    throw new ClientError("No dataset is specified for database " + dbName + " in reset");
                }
                dbSvc.installDataset(this, dataset, dbName);

                continue;
            }

            final TypedList collections = dbDesc.getList(KEY_COLLECTIONS);
            if ((collections == null) || collections.isEmpty()) {
                throw new ClientError("Null or empty collections list for database " + dbName + " in reset");
            }

            createDb(this, dbSvc, dbName, collections);
        }
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

    private static void createDb(
        @NonNull TestContext ctxt,
        @NonNull DatabaseService svc,
        @NonNull String dbName,
        @Nullable TypedList collections) {
        final List<String[]> collFqns = new ArrayList<>();
        if (collections != null) {
            for (int i = 0; i < collections.size(); i++) {
                final String fqn = collections.getString(i);
                if (fqn == null) { throw new ClientError("Null collection for database " + dbName + " in reset"); }
                collFqns.add(DatabaseService.parseCollectionFullName(fqn));
            }
        }
        svc.installDatabase(ctxt, dbName, collFqns);
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

        if (!new FileUtils().deleteRecursive(liveDbDir)) {
            Log.err(TAG, "Failed deleting db dir on reset: " + liveDbDir);
        }
    }
}
