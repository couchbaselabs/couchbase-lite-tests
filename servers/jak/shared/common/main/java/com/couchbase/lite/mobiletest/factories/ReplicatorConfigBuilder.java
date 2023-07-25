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
package com.couchbase.lite.mobiletest.factories;

import androidx.annotation.NonNull;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

import com.couchbase.lite.BasicAuthenticator;
import com.couchbase.lite.Collection;
import com.couchbase.lite.CollectionConfiguration;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.ReplicationFilter;
import com.couchbase.lite.ReplicatorConfiguration;
import com.couchbase.lite.ReplicatorType;
import com.couchbase.lite.SessionAuthenticator;
import com.couchbase.lite.URLEndpoint;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.data.TypedList;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;


@SuppressWarnings({"PMD.CyclomaticComplexity", "PMD.NPathComplexity"})
public class ReplicatorConfigBuilder {
    private static final String KEY_RESET = "reset";
    private static final String KEY_CONFIG = "config";
    private static final String KEY_DB = "database";
    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_ENDPOINT = "endpoint";
    private static final String KEY_TYPE = "replicatorType";
    private static final String TYPE_PUSH_AND_PULL = "pushandpull";
    private static final String TYPE_PUSH = "push";
    private static final String TYPE_PULL = "pull";
    private static final String KEY_IS_CONTINUOUS = "continuous";
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

    private static final List<String> LEGAL_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_DB);
        l.add(KEY_RESET);
        LEGAL_KEYS = Collections.unmodifiableList(l);
    }

    private static final List<String> LEGAL_CONFIG_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_DB);
        l.add(KEY_COLLECTIONS);
        l.add(KEY_ENDPOINT);
        l.add(KEY_TYPE);
        l.add(KEY_IS_CONTINUOUS);
        l.add(KEY_AUTHENTICATOR);
        LEGAL_CONFIG_KEYS = Collections.unmodifiableList(l);
    }

    private static final List<String> LEGAL_COLLECTION_KEYS;
    static {
        final List<String> l = new ArrayList<>();
        l.add(KEY_NAMES);
        l.add(KEY_CHANNELS);
        l.add(KEY_DOCUMENT_IDS);
        l.add(KEY_PUSH_FILTER);
        LEGAL_COLLECTION_KEYS = Collections.unmodifiableList(l);
    }


    @NonNull
    private final TypedMap req;
    @NonNull
    private final Memory memory;

    // This is a stateful object!!
    private boolean shouldReset;

    public ReplicatorConfigBuilder(@NonNull TypedMap req, @NonNull Memory memory) {
        this.req = req;
        this.memory = memory;
    }

    public boolean shouldReset() { return shouldReset; }

    @SuppressWarnings("deprecation")
    @NonNull
    public ReplicatorConfiguration build() {
        req.validate(LEGAL_KEYS);

        final Boolean reset = req.getBoolean(KEY_RESET);
        shouldReset = (reset != null) && reset;

        final TypedMap config = req.getMap(KEY_CONFIG);
        if (config == null) { throw new ClientError("No replicator configuration specified"); }
        config.validate(LEGAL_CONFIG_KEYS);

        final String uri = config.getString(KEY_ENDPOINT);
        if (uri == null) { throw new ClientError("Replicator configuration doesn't specify an endpoint"); }

        final URLEndpoint endpoint;
        try { endpoint = new URLEndpoint(new URI(uri)); }
        catch (URISyntaxException e) {
            throw new ClientError("Replicator configuration contains an unparsable endpoint: " + uri, e);
        }

        final String dbName = config.getString(KEY_DB);
        if (dbName == null) { throw new ClientError("Replicator configuration doesn't specify a database"); }

        final TypedList collections = config.getList(KEY_COLLECTIONS);
        if (collections == null) {
            throw new ClientError("Replicator configuration doesn't specify a list of collections");
        }

        final Database db = TestApp.getApp().getDbSvc().openDb(dbName, memory);

        final ReplicatorConfiguration replConfig;
        if (collections.isEmpty()) { replConfig = new ReplicatorConfiguration(db, endpoint); }
        else {
            replConfig = new ReplicatorConfiguration(endpoint);
            addCollections(db, collections, replConfig);
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

        final TypedMap authenticator = config.getMap(KEY_AUTHENTICATOR);
        if (authenticator != null) {
            if (authenticator.getKeys().size() > 1) {
                throw new ClientError("Replicator configuration specifies more than one authenticator");
            }

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

        return replConfig;
    }

    private void addCollections(
        @NonNull Database db,
        @NonNull TypedList spec,
        @NonNull ReplicatorConfiguration replConfig) {
        for (int i = 0; i < spec.size(); i++) {
            final TypedMap replCollection = spec.getMap(i);
            if (replCollection == null) { throw new ClientError("Replication collection spec is null: " + i); }
            replCollection.validate(LEGAL_COLLECTION_KEYS);

            final TypedList collFqns = replCollection.getList(KEY_NAMES);
            if (collFqns == null) {
                throw new ClientError("Replication collection doesn't specify collection names: " + i);
            }

            final Set<Collection> collections = new HashSet<>();
            for (int j = 0; j < collFqns.size(); j++) {
                final String collFqn = collFqns.getString(j);
                if (collFqn == null) { throw new ClientError("Empty collection name (" + i + ", " + j + ")"); }

                final String[] collName = collFqn.split("\\.");
                if ((collName.length != 2) || collName[0].isEmpty() || collName[1].isEmpty()) {
                    throw new ClientError("Cannot parse collection name: " + collFqn);
                }

                final Collection collection;
                try { collection = db.getCollection(collName[1], collName[0]); }
                catch (CouchbaseLiteException e) {
                    throw new CblApiFailure("Failed retrieving collection: " + collFqn, e);
                }
                collections.add(collection);
            }
            replConfig.addCollections(collections, buildCollectionConfig(replCollection));
        }
    }

    @NonNull
    private CollectionConfiguration buildCollectionConfig(@NonNull TypedMap spec) {
        final CollectionConfiguration collectionConfig = new CollectionConfiguration();

        final TypedList chSpec = spec.getList(KEY_CHANNELS);
        if (chSpec != null) {
            final int n = chSpec.size();
            final List<String> channels = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                final String channel = chSpec.getString(i);
                if (channel != null) { channels.add(channel); }
            }
            collectionConfig.setChannels(channels);
        }

        final TypedList docIdSpec = spec.getList(KEY_DOCUMENT_IDS);
        if (docIdSpec != null) {
            final int n = docIdSpec.size();
            final List<String> docIds = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                final String docId = docIdSpec.getString(i);
                if (docId != null) { docIds.add(docId); }
            }
            collectionConfig.setDocumentIDs(docIds);
        }

        final TypedMap pushFilter = spec.getMap(KEY_PUSH_FILTER);
        if (pushFilter != null) { collectionConfig.setPushFilter(buildReplicatorFilter(pushFilter)); }

        return collectionConfig;
    }

    @NonNull
    private BasicAuthenticator buildBasicAuthenticator(@NonNull TypedMap spec) {
        final String user = spec.getString(KEY_BASIC_AUTH_USER);
        if ((user == null) || user.isEmpty()) { throw new ClientError("Basic authenticator doesn't specify a user"); }

        final String pwd = spec.getString(KEY_BASIC_AUTH_PASSWORD);
        if ((pwd == null) || pwd.isEmpty()) { throw new ClientError("Basic authenticator doesn't specify a password"); }

        return new BasicAuthenticator(user, pwd.toCharArray());
    }

    @NonNull
    private SessionAuthenticator buildSessionAuthenticator(@NonNull TypedMap spec) {
        final String session = spec.getString(KEY_SESSION_AUTH_ID);
        if ((session == null) || session.isEmpty()) {
            throw new ClientError("Session authenticator doesn't specify a session id");
        }
        return new SessionAuthenticator(session, spec.getString(KEY_SESSION_AUTH_COOKIE));
    }


    @NonNull
    private ReplicationFilter buildReplicatorFilter(@NonNull TypedMap spec) {
        throw new ServerError("Filters not yet supported");
    }
}
