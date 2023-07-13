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

import java.net.URI;
import java.net.URISyntaxException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Map;

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
import com.couchbase.lite.mobiletest.TypedList;
import com.couchbase.lite.mobiletest.TypedMap;

@SuppressWarnings({"PMD.CyclomaticComplexity", "PMD.NPathComplexity"})
class ReplicatorConfigBuilder {
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
    private static final String KEY_COLLECTION = "collection";
    private static final String KEY_CHANNELS = "channels";
    private static final String KEY_DOCUMENT_IDS = "documentIDs";
    private static final String KEY_PUSH_FILTER = "pushFilter";

    @NonNull
    private final Map<String, Object> req;
    @NonNull
    private final Memory memory;

    ReplicatorConfigBuilder(@NonNull Map<String, Object> req, @NonNull Memory memory) {
        this.req = req;
        this.memory = memory;
    }

    @NonNull
    public ReplicatorConfiguration build() {
        final Object configSpec = req.get(KEY_CONFIG);
        if (!(configSpec instanceof Map)) {
            throw new IllegalStateException("Replicator configuration  does not specify a config");
        }
        final TypedMap config = new TypedMap((Map<?, ?>) configSpec, false);

        final String uri = config.getString(KEY_ENDPOINT);
        if (uri == null) {
            throw new IllegalStateException("Replicator configuration does not specify an endpoint");
        }

        final URLEndpoint endpoint;
        try { endpoint = new URLEndpoint(new URI(uri)); }
        catch (URISyntaxException e) {
            throw new IllegalStateException("Replicator configuration contains an unparsable endpoint: " + uri, e);
        }

        final String dbName = config.getString(KEY_DB);
        if (dbName == null) {
            throw new IllegalStateException("Replicator configuration does not specify a database");
        }

        final List<Object> collections = config.getList(KEY_COLLECTIONS);
        if (collections == null) {
            throw new IllegalStateException("Replicator configuration does not specify a list of collections");
        }

        final Database db = TestApp.getApp().getDbMgr().openDb(dbName, memory);

        final ReplicatorConfiguration replConfig;
        if (collections.isEmpty()) { replConfig = new ReplicatorConfiguration(db, endpoint); }
        else {
            replConfig = new ReplicatorConfiguration(endpoint);
            addCollections(db, new TypedList(collections), replConfig);
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
                    throw new IllegalStateException("Unrecognized replicator type: " + replType);
            }
        }

        final Boolean isContinuous = config.getBoolean(KEY_IS_CONTINUOUS);
        if (isContinuous != null) { replConfig.setContinuous(isContinuous); }

        final Map<String, Object> auth = config.getMap(KEY_AUTHENTICATOR);
        if (auth != null) {
            final TypedMap authenticator = new TypedMap(auth);
            final String authType = authenticator.getString(KEY_AUTH_TYPE);
            if (authType == null) {
                throw new IllegalStateException("Replicator authenticator does not specify a type");
            }
            switch (authType.toLowerCase(Locale.getDefault())) {
                case AUTH_TYPE_BASIC:
                    replConfig.setAuthenticator(buildBasicAuthenticator(authenticator));
                    break;
                case AUTH_TYPE_SESSION:
                    replConfig.setAuthenticator(buildSessionAuthenticator(authenticator));
                    break;
                default:
                    throw new IllegalStateException("Unrecognized authenticator type: " + replType);
            }
        }

        return replConfig;
    }

    private void addCollections(
        @NonNull Database db,
        @NonNull TypedList spec,
        @NonNull ReplicatorConfiguration replConfig) {
        for (int i = 0; i < spec.size(); i++) {
            final Map<String, Object> replColl = spec.getMap(i);
            if (replColl == null) {
                throw new IllegalStateException("Replication collection spec is null: " + i);
            }
            final TypedMap replCollection = new TypedMap(replColl);
            final String collFqn = replCollection.getString(KEY_COLLECTION);
            if (collFqn == null) {
                throw new IllegalStateException("Replication collection does not specify a collection: " + i);
            }
            final String[] collName = collFqn.split("\\.");
            if ((collName.length != 2) || collName[0].isEmpty() || collName[1].isEmpty()) {
                throw new IllegalStateException("Cannot parse collection name: " + collFqn);
            }

            final Collection collection;
            try { collection = db.createCollection(collName[1], collName[0]); }
            catch (CouchbaseLiteException e) {
                throw new IllegalStateException("Failed creating collection: " + collFqn, e);
            }

            replConfig.addCollection(collection, buildCollectionConfig(replCollection));
        }
    }

    @NonNull
    private CollectionConfiguration buildCollectionConfig(@NonNull TypedMap spec) {
        final CollectionConfiguration collectionConfig = new CollectionConfiguration();

        final List<Object> chList = spec.getList(KEY_CHANNELS);
        if (chList != null) {
            final TypedList chSpec = new TypedList(chList);
            final int n = chSpec.size();
            final List<String> channels = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                final String channel = chSpec.getString(i);
                if (channel != null) { channels.add(channel); }
            }
            collectionConfig.setChannels(channels);
        }

        final List<Object> docIdList = spec.getList(KEY_DOCUMENT_IDS);
        if (docIdList != null) {
            final TypedList docIdSpec = new TypedList(chList);
            final int n = docIdSpec.size();
            final List<String> docIds = new ArrayList<>(n);
            for (int i = 0; i < n; i++) {
                final String docId = docIdSpec.getString(i);
                if (docId != null) { docIds.add(docId); }
            }
            collectionConfig.setDocumentIDs(docIds);
        }

        final Map<String, Object> pushFilter = spec.getMap(KEY_PUSH_FILTER);
        if (pushFilter != null) { collectionConfig.setPushFilter(buildReplicatorFilter(new TypedMap(pushFilter))); }

        return collectionConfig;
    }

    @NonNull
    private ReplicationFilter buildReplicatorFilter(@NonNull TypedMap map) {
        throw new IllegalStateException("Filters not yet implemented");
    }

    @NonNull
    private BasicAuthenticator buildBasicAuthenticator(@NonNull TypedMap spec) {
        final String user = spec.getString(KEY_BASIC_AUTH_USER);
        if ((user == null) || user.isEmpty()) {
            throw new IllegalStateException("Basic authenticator does not specify a user");
        }
        final String pwd = spec.getString(KEY_BASIC_AUTH_PASSWORD);
        if ((pwd == null) || pwd.isEmpty()) {
            throw new IllegalStateException("Basic authenticator does not specify a password");
        }
        return new BasicAuthenticator(user, pwd.toCharArray());
    }

    @NonNull
    private SessionAuthenticator buildSessionAuthenticator(@NonNull TypedMap spec) {
        final String session = spec.getString(KEY_SESSION_AUTH_ID);
        if ((session == null) || session.isEmpty()) {
            throw new IllegalStateException("Session authenticator does not specify a session id");
        }
        return new SessionAuthenticator(session, spec.getString(KEY_SESSION_AUTH_COOKIE));
    }
}
