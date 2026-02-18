//
// Copyright (c) 2025 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.android.mobiletest.endpoints.v1;

import android.text.TextUtils;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.security.GeneralSecurityException;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import java.util.function.Supplier;

import com.couchbase.lite.Conflict;
import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.Dictionary;
import com.couchbase.lite.Document;
import com.couchbase.lite.KeyStoreUtils;
import com.couchbase.lite.MultipeerCertificateAuthenticator;
import com.couchbase.lite.MultipeerCollectionConfiguration;
import com.couchbase.lite.MultipeerReplicatorConfiguration;
import com.couchbase.lite.MutableArray;
import com.couchbase.lite.MutableDictionary;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.PeerInfo;
import com.couchbase.lite.PeerReplicatorStatus;
import com.couchbase.lite.TLSIdentity;
import com.couchbase.lite.android.mobiletest.services.MultipeerReplicatorService;
import com.couchbase.lite.internal.utils.PlatformUtils;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.endpoints.v1.BaseReplicatorManager;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class MultipeerReplicatorManager extends BaseReplicatorManager {
    private static final String TAG = "MP_REPL_MGR_V1";

    private static final String KEY_ID = "peerID";
    private static final String KEY_STATUS = "status";
    private static final String KEY_REPLICATORS = "replicators";

    // Create replicator
    private static final String KEY_PEER_GROUP = "peerGroupID";
    private static final String KEY_DATABASE = "database";
    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_IDENTITY = "identity";
    private static final String KEY_AUTHENTICATOR = "authenticator";

    // Identity
    private static final String KEY_IDENTITY_ENCODING = "encoding";
    private static final String KEY_IDENTITY_DATA = "data";
    private static final String KEY_IDENTITY_PASSWORD = "password";

    // Authenticator
    private static final String KEY_AUTH_CERT = "certificate";
    private static final String TYPE_CERT_AUTH_TYPE = "CA-CERT";


    private interface ConfigurableConflictResolver extends MultipeerCollectionConfiguration.ConflictResolver {
        void configure(@Nullable TypedMap config);
    }

    private static class LocalWinsResolver implements ConfigurableConflictResolver {
        @Override
        public void configure(@Nullable TypedMap config) {
            // no configuration needed
        }

        @Nullable
        @Override
        public Document resolve(@NonNull PeerInfo.PeerId peerId, @NonNull Conflict conflict) {
            return conflict.getLocalDocument();
        }
    }

    private static class RemoteWinsResolver implements ConfigurableConflictResolver {
        @Override
        public void configure(@Nullable TypedMap config) {
            // no configuration needed
        }

        @Nullable
        @Override
        public Document resolve(@NonNull PeerInfo.PeerId peerId, @NonNull Conflict conflict) {
            return conflict.getRemoteDocument();
        }
    }

    private static class DeleteResolver implements ConfigurableConflictResolver {
        @Override
        public void configure(@Nullable TypedMap config) {
            // no configuration needed
        }

        @Nullable
        @Override
        public Document resolve(@NonNull PeerInfo.PeerId peerId, @NonNull Conflict conflict) { return null; }
    }

    private static class MergeResolver implements ConfigurableConflictResolver {
        private static final String KEY_PROPERTY = "property";

        private static final Set<String> MERGE_RESOLVER_KEYS;
        static {
            final Set<String> l = new HashSet<>();
            l.add(KEY_PROPERTY);
            MERGE_RESOLVER_KEYS = Collections.unmodifiableSet(l);
        }


        private String docProp;

        @Override
        public void configure(@Nullable TypedMap config) {
            if (config == null) { throw new ClientError("Merge resolver requires configuration"); }

            config.validate(MERGE_RESOLVER_KEYS);

            final String prop = config.getString(KEY_PROPERTY);
            if (prop == null) { throw new ClientError("Merge resolver requires a property name"); }

            docProp = prop;
        }

        @Nullable
        @Override
        public Document resolve(@NonNull PeerInfo.PeerId peerId, @NonNull Conflict conflict) {
            final Document localDoc = conflict.getLocalDocument();
            final Document remoteDoc = conflict.getRemoteDocument();
            if ((localDoc == null) || (remoteDoc == null)) { return null; }

            final MutableArray mergedVal = new MutableArray();
            mergedVal.addValue(localDoc.getValue(docProp));
            mergedVal.addValue(remoteDoc.getValue(docProp));

            final MutableDocument mergedDoc = localDoc.toMutable();
            mergedDoc.setValue(docProp, mergedVal);

            return mergedDoc;
        }
    }

    private static class MergeDictResolver implements ConfigurableConflictResolver {
        private static final String KEY_PROPERTY = "property";

        private static final Set<String> MERGE_DICT_RESOLVER_KEYS = Set.of(KEY_PROPERTY);

        private String docProp;

        @Override
        public void configure(@Nullable TypedMap config) {
            if (config == null) { throw new ClientError("Merge resolver requires configuration"); }

            config.validate(MERGE_DICT_RESOLVER_KEYS);

            final String prop = config.getString(KEY_PROPERTY);
            if (prop == null) { throw new ClientError("Merge resolver requires a property name"); }

            docProp = prop;
        }

        @Nullable
        @Override
        public Document resolve(@NonNull PeerInfo.PeerId peerId, @NonNull Conflict conflict) {
            final Document localDoc = conflict.getLocalDocument();
            final Document remoteDoc = conflict.getRemoteDocument();
            if ((localDoc == null) || (remoteDoc == null)) { return null; }

            final MutableDocument doc = remoteDoc.toMutable();

            final Dictionary localDict = localDoc.getDictionary(docProp);
            final Dictionary remoteDict = remoteDoc.getDictionary(docProp);

            Log.p(TAG, "+++++++ localDoc : " + localDoc.toMap());
            Log.p(TAG, "+++++++ remoteDoc : " + remoteDoc.toMap());

            if (localDict != null) {
                Log.p(TAG, "+++++++ localDict : " + localDict.toString());
            } else {
                Log.p(TAG, "+++++++ localDict : NULL");
            }

            if (remoteDict != null) {
                Log.p(TAG, "+++++++ remoteDict : " + remoteDict.toString());
            } else {
                Log.p(TAG, "+++++++ remoteDict : NULL");
            }

            if(localDict == null || remoteDict == null) {
                doc.setString("foo", "bar");
                return doc.setString(docProp, "Both values are not dictionary");
            }

            final MutableDictionary mergedDict = localDict.toMutable();
            for(String key : remoteDict) {
                final Object remoteValue = remoteDict.getValue(key);
                if(mergedDict.contains(key) && !Objects.equals(remoteValue, mergedDict.getValue(key))) {
                    return doc.setString(key, String.format("Conflicting values found at key named %s", key));
                }

                mergedDict.setValue(key, remoteValue);
            }

            return doc.setDictionary(docProp, mergedDict);
        }
    }

    private static final Set<String> LEGAL_CREATE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_COLLECTIONS);
        l.add(KEY_PEER_GROUP);
        l.add(KEY_IDENTITY);
        l.add(KEY_AUTHENTICATOR);
        LEGAL_CREATE_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_COLLECTION_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_NAMES);
        l.add(KEY_DOCUMENT_IDS);
        l.add(KEY_PUSH_FILTER);
        l.add(KEY_PULL_FILTER);
        l.add(KEY_CONFLICT_RESOLVER);
        LEGAL_COLLECTION_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_IDENTITY_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_IDENTITY_ENCODING);
        l.add(KEY_IDENTITY_DATA);
        l.add(KEY_IDENTITY_PASSWORD);
        LEGAL_IDENTITY_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_CERTIFICATE_AUTH_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_AUTH_TYPE);
        l.add(KEY_AUTH_CERT);
        LEGAL_CERTIFICATE_AUTH_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Map<String, Supplier<ConfigurableConflictResolver>> CONFLICT_RESOLVER_FACTORIES = Map.of(
            "local-wins", LocalWinsResolver::new,
            "remote-wins", RemoteWinsResolver::new,
            "delete", DeleteResolver::new,
            "merge", MergeResolver::new,
            "merge-dict", MergeDictResolver::new
    );


    @NonNull
    private final MultipeerReplicatorService replSvc;

    public MultipeerReplicatorManager(@NonNull DatabaseService dbSvc, @NonNull MultipeerReplicatorService replSvc) {
        super(dbSvc);
        this.replSvc = replSvc;
    }

    @NonNull
    public Map<String, Object> createRepl(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        Log.p(TAG, "starting multipeer replicator");
        req.validate(LEGAL_CREATE_KEYS);

        final Map<String, Object> ret = new HashMap<>();
        ret.put(KEY_REPL_ID, replSvc.startReplicator(ctxt, buildConfig(ctxt, req)));
        return ret;
    }

    @NonNull
    public Map<String, Object> getReplStatus(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_REPL_ID_KEYS);

        final String replId = req.getString(KEY_REPL_ID);
        if (replId == null) { throw new ClientError("Replicator id not specified"); }

        final List<Map<String, Object>> peerInfoList = new ArrayList<>();
        final Map<PeerInfo.PeerId, PeerReplicatorStatus> neighbors = replSvc.getStatus(ctxt, replId);
        final Map<String, Object> peerInfoMap = new HashMap<>();
        neighbors.forEach((key, value) -> {
            peerInfoMap.put(KEY_ID, key.toString());
            peerInfoMap.put(KEY_STATUS, parseReplStatus(value.getStatus(), null));
            peerInfoList.add(peerInfoMap);
        });

        final Map<String, Object> resp = new HashMap<>();
        resp.put(KEY_REPLICATORS, peerInfoList);

        return resp;
    }

    @NonNull
    public Map<String, Object> stopRepl(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        Log.p(TAG, "stopping multipeer replicator");
        req.validate(LEGAL_REPL_ID_KEYS);

        final String replId = req.getString(KEY_REPL_ID);
        if (replId == null) { throw new ClientError("Multipeer Replicator stop doesn't specify the replicator id"); }

        replSvc.stopReplicator(ctxt, replId);

        return Collections.emptyMap();
    }

    @NonNull
    private MultipeerReplicatorConfiguration buildConfig(@NonNull TestContext ctxt, @NonNull TypedMap config) {
        final String peerGroup = config.getString(KEY_PEER_GROUP);
        if (peerGroup == null) {
            throw new ClientError("Multipeer Replicator configuration doesn't specify a peer group ID");
        }

        final MultipeerReplicatorConfiguration.Builder builder = new MultipeerReplicatorConfiguration.Builder();
        builder.setPeerGroupID(peerGroup);

        final String dbName = config.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Multipeer Replicator configuration doesn't specify a database"); }

        final TypedList collections = config.getList(KEY_COLLECTIONS);
        if ((collections == null) || collections.isEmpty()) {
            throw new ClientError("Multipeer Replicator specifies a null or empty list of collections");
        }

        final Database db = dbSvc.getOpenDb(ctxt, dbName);

        addCollections(db, collections, builder, ctxt);

        final TypedMap identity = config.getMap(KEY_IDENTITY);
        if ((identity == null) || (identity.isEmpty())) {
            throw new ClientError("Multipeer Replicator specifies a null or empty identity");
        }
        addIdentity(identity, builder);

        final TypedMap authSpec = config.getMap(KEY_AUTHENTICATOR);
        if (authSpec != null) { addCertificateAuthenticator(authSpec, builder); }
        else { builder.setAuthenticator(new MultipeerCertificateAuthenticator(new MultipeerCertificateAuthenticator.AuthenticationDelegate() {
            @Override
            public boolean authenticate(@NonNull PeerInfo.PeerId peer, @NonNull List<X509Certificate> certs) {
                return true;
            }
        })); }

        return builder.build();
    }

    private void addCollections(
        @NonNull Database db,
        @NonNull TypedList collectionSpecs,
        @NonNull MultipeerReplicatorConfiguration.Builder configBuilder,
        @NonNull TestContext ctxt) {
        for (int i = 0; i < collectionSpecs.size(); i++) {
            final TypedMap collectionsSpec = collectionSpecs.getMap(i);
            if ((collectionsSpec == null) || collectionsSpec.isEmpty()) {
                throw new ClientError("Multipeer Replicator specifies a null or empty collection spec @" + i);
            }
            collectionsSpec.validate(LEGAL_COLLECTION_KEYS);

            final TypedList collectionNames = collectionsSpec.getList(KEY_NAMES);
            if ((collectionNames == null) || (collectionNames.isEmpty())) {
                throw new ClientError("Multipeer Replicator specifies a null or empty list of collection names@" + i);
            }

            List<MultipeerCollectionConfiguration> collectionConfigs = new ArrayList<>();
            // All of the collections named in the array get the same configuration
            for (int j = 0; j < collectionNames.size(); j++) {
                final String collectionName = collectionNames.getString(j);
                if (StringUtils.isEmpty(collectionName)) {
                    throw new ClientError("Empty collection name in multipeer collection spec @" + i + "/" + j);
                }
                final MultipeerCollectionConfiguration.Builder collectionBuilder
                    = new MultipeerCollectionConfiguration.Builder(dbSvc.getCollection(ctxt, db, collectionName));

                collectionConfigs.add(buildCollectionConfig(collectionsSpec, collectionBuilder));
            }

            configBuilder.setCollections(collectionConfigs);
        }
    }

    @NonNull
    private MultipeerCollectionConfiguration buildCollectionConfig(
        @NonNull TypedMap spec,
        @NonNull MultipeerCollectionConfiguration.Builder builder) {
        final List<String> docIds = getList(spec.getList(KEY_DOCUMENT_IDS));
        if (docIds != null) { builder.setDocumentIDs(docIds); }

        final TypedMap pushFilter = spec.getMap(KEY_PUSH_FILTER);
        if (pushFilter != null) { builder.setPushFilter(buildReplicatorFilter(pushFilter)); }

        final TypedMap pullFilter = spec.getMap(KEY_PULL_FILTER);
        if (pullFilter != null) { builder.setPullFilter(buildReplicatorFilter(pullFilter)); }

        final TypedMap conflictResolver = spec.getMap(KEY_CONFLICT_RESOLVER);
        if (conflictResolver != null) { builder.setConflictResolver(buildConflictResolver(conflictResolver)); }

        return builder.build();
    }

    @NonNull
    private MultipeerCollectionConfiguration.ReplicationFilter buildReplicatorFilter(@NonNull TypedMap spec) {
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
    private MultipeerCollectionConfiguration.ReplicationFilter buildDocIdFilter(@Nullable TypedMap spec) {
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

    @NonNull
    protected final MultipeerCollectionConfiguration.ConflictResolver buildConflictResolver(@NonNull TypedMap spec) {
        final String name = spec.getString(KEY_NAME);
        if (name == null) { throw new ClientError("No name specified for the conflict resolver"); }

        final Supplier<ConfigurableConflictResolver> resolverFactory
            = CONFLICT_RESOLVER_FACTORIES.get(name.toLowerCase(Locale.US).trim());
        if (resolverFactory == null) { throw new ClientError("Unrecognized conflict resolver: " + name); }

        final ConfigurableConflictResolver resolver = resolverFactory.get();
        resolver.configure(spec.getMap(KEY_PARAMS));

        return resolver;
    }

    @SuppressWarnings("PMD.ExceptionAsFlowControl")
    private void addIdentity(TypedMap identitySpec, MultipeerReplicatorConfiguration.Builder builder) {
        identitySpec.validate(LEGAL_IDENTITY_KEYS);

        final byte[] data = PlatformUtils.getDecoder().decodeString(identitySpec.getString(KEY_IDENTITY_DATA));
        if (data == null) { throw new ClientError("Could not decode identity data for Multipeer Replicator"); }

        final String encoding = identitySpec.getString(KEY_IDENTITY_ENCODING);
        if (encoding == null) { throw new ClientError("Null encoding for identity in Multipeer Replicator"); }

        final String password = identitySpec.getString(KEY_IDENTITY_PASSWORD);
        if (password == null) { throw new ClientError("Null password for identity in Multipeer Replicator"); }
        final char[] pwdChars = password.toCharArray();

        try {
            final String keyAlias = "android-multipeer-" + builder.getPeerGroupID();

            try (InputStream in = new ByteArrayInputStream(data)) {
                KeyStoreUtils.importEntry(encoding, in, pwdChars, "cbltest", pwdChars, keyAlias);
            }
            catch (GeneralSecurityException | IOException e) {
                throw new CouchbaseLiteException("Failed to import identity", e);
            }

            final TLSIdentity identity = TLSIdentity.getIdentity(keyAlias);
            if (identity == null) {
                throw new CouchbaseLiteException("Failed to create identity");
            }

            builder.setIdentity(identity);
        }
        catch (CouchbaseLiteException e) {
            throw new CblApiFailure("Could not create identity for Multipeer Replicator", e);
        }
    }

    private void addCertificateAuthenticator(
        @NonNull TypedMap spec,
        MultipeerReplicatorConfiguration.Builder builder) {
        spec.validate(LEGAL_CERTIFICATE_AUTH_KEYS);

        final String type = spec.getString(TYPE_CERT_AUTH_TYPE);
        if (!TYPE_CERT_AUTH_TYPE.equals(type)) { throw new ClientError("Unrecognized certificate type: " + type); }

        final String cert = spec.getString(KEY_AUTH_CERT);
        if (TextUtils.isEmpty(cert)) { throw new ClientError("Null or empty certificate"); }

        // decode the CA-CERT string

        //builder.setAuthenticator(new MultipeerCertificateAuthenticator(cert));
    }
}
