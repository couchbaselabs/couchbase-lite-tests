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
package com.couchbase.lite.mobiletest.endpoints.v1;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.BasicAuthenticator;
import com.couchbase.lite.CollectionConfiguration;
import com.couchbase.lite.Database;
import com.couchbase.lite.ReplicationFilter;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorConfiguration;
import com.couchbase.lite.ReplicatorType;
import com.couchbase.lite.SessionAuthenticator;
import com.couchbase.lite.URLEndpoint;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.ReplicatorService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.Log;


public class CreateRepl {
    private static final String TAG = "CREATE_REPL_V1";

    private static final String KEY_REPL_ID = "id";

    private static final String KEY_RESET = "reset";
    private static final String KEY_CONFIG = "config";
    private static final String KEY_DATABASE = "database";
    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_ENDPOINT = "endpoint";
    private static final String KEY_TYPE = "replicatorType";
    private static final String TYPE_PUSH_AND_PULL = "pushandpull";
    private static final String TYPE_PUSH = "push";
    private static final String TYPE_PULL = "pull";
    private static final String KEY_IS_CONTINUOUS = "continuous";
    private static final String KEY_ENABLE_DOC_LISTENER = "enableDocumentListener";
    private static final String KEY_AUTHENTICATOR = "authenticator";
    private static final String KEY_AUTH_TYPE = "type";
    private static final String AUTH_TYPE_BASIC = "basic";
    private static final String KEY_BASIC_AUTH_USER = "username";
    private static final String KEY_BASIC_AUTH_PASSWORD = "password";
    private static final String AUTH_TYPE_SESSION = "session";
    private static final String KEY_SESSION_AUTH_ID = "sessionID";
    private static final String KEY_SESSION_AUTH_COOKIE = "cookieName";
    private static final String KEY_NAMES = "names";
    private static final String KEY_CHANNELS = "channels";
    private static final String KEY_DOCUMENT_IDS = "documentIDs";
    private static final String KEY_PUSH_FILTER = "pushFilter";
    private static final String KEY_PULL_FILTER = "pullFilter";
    private static final String KEY_NAME = "name";
    private static final String KEY_PARAMS = "params";
    private static final String FILTER_DELETED = "deletedDocumentsOnly";
    private static final String FILTER_DOC_ID = "documentIDs";
    private static final String KEY_DOC_IDS = "documentIDs";
    private static final String KEY_ENABLE_AUTOPURGE = "enableAutoPurge";

    private static final Set<String> LEGAL_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_CONFIG);
        l.add(KEY_RESET);
        LEGAL_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_CONFIG_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_COLLECTIONS);
        l.add(KEY_ENDPOINT);
        l.add(KEY_TYPE);
        l.add(KEY_IS_CONTINUOUS);
        l.add(KEY_AUTHENTICATOR);
        l.add(KEY_ENABLE_DOC_LISTENER);
        l.add(KEY_ENABLE_AUTOPURGE);
        LEGAL_CONFIG_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_COLLECTION_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_NAMES);
        l.add(KEY_CHANNELS);
        l.add(KEY_DOCUMENT_IDS);
        l.add(KEY_PUSH_FILTER);
        l.add(KEY_PULL_FILTER);
        LEGAL_COLLECTION_KEYS = Collections.unmodifiableSet(l);
    }


    private static final Set<String> LEGAL_BASIC_AUTH_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_AUTH_TYPE);
        l.add(KEY_BASIC_AUTH_USER);
        l.add(KEY_BASIC_AUTH_PASSWORD);
        LEGAL_BASIC_AUTH_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_SESSION_AUTH_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_AUTH_TYPE);
        l.add(KEY_SESSION_AUTH_ID);
        l.add(KEY_SESSION_AUTH_COOKIE);
        LEGAL_SESSION_AUTH_KEYS = Collections.unmodifiableSet(l);
    }

    @NonNull
    private final DatabaseService dbSvc;
    @NonNull
    private final ReplicatorService replSvc;

    public CreateRepl(@NonNull DatabaseService dbSvc, @NonNull ReplicatorService replSvc) {
        this.dbSvc = dbSvc;
        this.replSvc = replSvc;
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @NonNull
    public Map<String, Object> createRepl(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_KEYS);

        final TypedMap config = req.getMap(KEY_CONFIG);
        if (config == null) { throw new ClientError("No replicator configuration specified"); }
        config.validate(LEGAL_CONFIG_KEYS);

        final ReplicatorConfiguration replConfig = buildConfig(ctxt, config);
        final Replicator repl = new Replicator(replConfig);
        final String replId = replSvc.addRepl(ctxt, repl);

        final Boolean enableListener = config.getBoolean(KEY_ENABLE_DOC_LISTENER);
        if ((enableListener != null) && enableListener) {
            replSvc.addDocListener(ctxt, replId, repl);
            Log.p(TAG, "Added doc listener: " + replId);
        }

        final Boolean shouldReset = req.getBoolean(KEY_RESET);
        repl.start((shouldReset != null) && shouldReset);
        Log.p(TAG, "Started replicator: " + replId);

        final Map<String, Object> ret = new HashMap<>();
        ret.put(KEY_REPL_ID, replId);
        return ret;
    }

    @SuppressWarnings({"deprecation", "PMD.NPathComplexity"})
    @NonNull
    public ReplicatorConfiguration buildConfig(@NonNull TestContext ctxt, @NonNull TypedMap config) {
        final String uri = config.getString(KEY_ENDPOINT);
        if (uri == null) { throw new ClientError("Replicator configuration doesn't specify an endpoint"); }

        final URLEndpoint endpoint;
        try { endpoint = new URLEndpoint(new URI(uri)); }
        catch (URISyntaxException e) {
            throw new ClientError("Replicator configuration contains an unparsable endpoint: " + uri, e);
        }

        final String dbName = config.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Replicator configuration doesn't specify a database"); }

        final TypedList collections = config.getList(KEY_COLLECTIONS);
        if (collections == null) {
            throw new ClientError("Replicator configuration doesn't specify a list of collections");
        }

        final Database db = TestApp.getApp().getDbSvc().getOpenDb(ctxt, dbName);

        final ReplicatorConfiguration replConfig;
        if (collections.isEmpty()) { replConfig = new ReplicatorConfiguration(db, endpoint); }
        else {
            replConfig = new ReplicatorConfiguration(endpoint);
            addCollections(db, collections, replConfig, ctxt);
        }

        final String replType = config.getString(KEY_TYPE);
        if (replType != null) {
            switch (replType.toLowerCase(Locale.getDefault())) {
                case TYPE_PUSH_AND_PULL:
                    replConfig.setType(ReplicatorType.PUSH_AND_PULL);
                    break;
                case TYPE_PUSH:
                    replConfig.setType(ReplicatorType.PUSH);
                    break;
                case TYPE_PULL:
                    replConfig.setType(ReplicatorType.PULL);
                    break;
                default:
                    throw new ClientError("Unrecognized replicator type: " + replType);
            }
        }

        final Boolean isContinuous = config.getBoolean(KEY_IS_CONTINUOUS);
        if (isContinuous != null) { replConfig.setContinuous(isContinuous); }

        final Boolean enableAutoPurge = config.getBoolean(KEY_ENABLE_AUTOPURGE);
        if (enableAutoPurge != null) { replConfig.setAutoPurgeEnabled(enableAutoPurge); }

        final TypedMap authenticator = config.getMap(KEY_AUTHENTICATOR);
        if (authenticator != null) {
            final String authType = authenticator.getString(KEY_AUTH_TYPE);
            if (authType == null) { throw new ClientError("Replicator authenticator doesn't specify a type"); }

            switch (authType.toLowerCase(Locale.getDefault())) {
                case AUTH_TYPE_BASIC:
                    replConfig.setAuthenticator(buildBasicAuthenticator(authenticator));
                    break;
                case AUTH_TYPE_SESSION:
                    replConfig.setAuthenticator(buildSessionAuthenticator(authenticator));
                    break;
                default:
                    throw new ClientError("Unrecognized authenticator type: " + replType);
            }
        }

        Log.p(TAG, "Build config: " + replConfig);
        return replConfig;
    }

    private void addCollections(
        @NonNull Database db,
        @NonNull TypedList spec,
        @NonNull ReplicatorConfiguration replConfig,
        @NonNull TestContext ctxt
    ) {
        for (int i = 0; i < spec.size(); i++) {
            final TypedMap replCollection = spec.getMap(i);
            if (replCollection == null) { throw new ClientError("Replication collection spec is null: " + i); }
            replCollection.validate(LEGAL_COLLECTION_KEYS);

            final TypedList collectionNames = replCollection.getList(KEY_NAMES);
            if (collectionNames == null) { throw new ClientError("no collections specified"); }

            replConfig.addCollections(
                dbSvc.getCollections(ctxt, db, collectionNames),
                buildCollectionConfig(replCollection));
        }
    }

    @NonNull
    private CollectionConfiguration buildCollectionConfig(@NonNull TypedMap spec) {
        final CollectionConfiguration collectionConfig = new CollectionConfiguration();

        final List<String> channels = getList(spec.getList(KEY_CHANNELS));
        if (channels != null) { collectionConfig.setChannels(channels); }

        final List<String> docIds = getList(spec.getList(KEY_DOCUMENT_IDS));
        if (docIds != null) { collectionConfig.setDocumentIDs(docIds); }

        final TypedMap pushFilter = spec.getMap(KEY_PUSH_FILTER);
        if (pushFilter != null) { collectionConfig.setPushFilter(buildReplicatorFilter(pushFilter)); }

        final TypedMap pullFilter = spec.getMap(KEY_PULL_FILTER);
        if (pullFilter != null) { collectionConfig.setPullFilter(buildReplicatorFilter(pullFilter)); }

        return collectionConfig;
    }

    @NonNull
    private BasicAuthenticator buildBasicAuthenticator(@NonNull TypedMap spec) {
        spec.validate(LEGAL_BASIC_AUTH_KEYS);

        final String user = spec.getString(KEY_BASIC_AUTH_USER);
        if ((user == null) || user.isEmpty()) { throw new ClientError("Basic authenticator doesn't specify a user"); }

        final String pwd = spec.getString(KEY_BASIC_AUTH_PASSWORD);
        if ((pwd == null) || pwd.isEmpty()) { throw new ClientError("Basic authenticator doesn't specify a password"); }

        return new BasicAuthenticator(user, pwd.toCharArray());
    }

    @NonNull
    private SessionAuthenticator buildSessionAuthenticator(@NonNull TypedMap spec) {
        spec.validate(LEGAL_SESSION_AUTH_KEYS);

        final String session = spec.getString(KEY_SESSION_AUTH_ID);
        if ((session == null) || session.isEmpty()) {
            throw new ClientError("Session authenticator doesn't specify a session id");
        }
        return new SessionAuthenticator(session, spec.getString(KEY_SESSION_AUTH_COOKIE));
    }

    @Nullable
    private List<String> getList(@Nullable TypedList spec) {
        if (spec == null) { return null; }
        final int n = spec.size();
        final List<String> list = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            final String item = spec.getString(i);
            if (item != null) { list.add(item); }
        }
        return list;
    }

    @NonNull
    private ReplicationFilter buildReplicatorFilter(@NonNull TypedMap spec) {
        final String name = spec.getString(KEY_NAME);
        if (name == null) { throw new ClientError("Filter doesn't specify a name"); }
        switch (name) {
            case FILTER_DOC_ID:
                 return buildDocIdFilter(spec.getMap(KEY_PARAMS));
            case FILTER_DELETED:
                return replSvc.getDeletedDocFilter();
            default:
                throw new ClientError("Unrecognized filter name: " + name);
        }
    }

    @NonNull
    private ReplicationFilter buildDocIdFilter(@Nullable TypedMap spec) {
        if (spec == null) { throw new ClientError("DocId filter specifies no doc ids"); }

        final TypedMap documentIds = spec.getMap(KEY_DOC_IDS);
        if (documentIds == null) { throw new ClientError("DocId filter specifies no doc ids"); }

        final Set<String> permitted = new HashSet<>();

        final Set<String> collections = documentIds.getKeys();
        for (String collection: collections) {
            final TypedList collectionDocs = documentIds.getList(collection);
            if (collectionDocs == null) {
                throw new ClientError("DocId filter: no doc ids specified for collection " + collection);
            }
            final int n = collectionDocs.size();
            for (int i = 0; i < n; i++) { permitted.add(collection + "." + collectionDocs.getString(i)); }
        }

        return replSvc.getDocIdFilter(permitted);
    }
}
