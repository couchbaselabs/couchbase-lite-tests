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

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.URISyntaxException;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.function.Supplier;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.BasicAuthenticator;
import com.couchbase.lite.Collection;
import com.couchbase.lite.CollectionConfiguration;
import com.couchbase.lite.Conflict;
import com.couchbase.lite.ConflictResolver;
import com.couchbase.lite.Database;
import com.couchbase.lite.Document;
import com.couchbase.lite.DocumentReplication;
import com.couchbase.lite.MutableArray;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.ReplicationFilter;
import com.couchbase.lite.Replicator;
import com.couchbase.lite.ReplicatorConfiguration;
import com.couchbase.lite.ReplicatorStatus;
import com.couchbase.lite.ReplicatorType;
import com.couchbase.lite.SessionAuthenticator;
import com.couchbase.lite.URLEndpoint;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.services.ReplicatorService;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;


@SuppressWarnings({"PMD.ExcessiveImports", "PMD.CyclomaticComplexity"})
@SuppressFBWarnings("EI_EXPOSE_REP2")
public class ReplicatorManager extends BaseReplicatorManager {
    private static final String TAG = "REPL_MGR_V1";

    // Create replicator
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
    private static final String KEY_SESSION_AUTH_ID = "sessionID";
    private static final String KEY_SESSION_AUTH_COOKIE = "cookieName";
    private static final String KEY_ENABLE_AUTOPURGE = "enableAutoPurge";
    private static final String KEY_PINNED_CERT = "pinnedServerCert";

    private interface ConfigurableConflictResolver extends ConflictResolver {
        void configure(@Nullable TypedMap config);
    }

    private static class LocalWinsResolver implements ConfigurableConflictResolver {
        @Override
        public void configure(@Nullable TypedMap config) {
            // no configuration needed
        }

        @Nullable
        @Override
        public Document resolve(@NonNull Conflict conflict) { return conflict.getLocalDocument(); }
    }

    private static class RemoteWinsResolver implements ConfigurableConflictResolver {
        @Override
        public void configure(@Nullable TypedMap config) {
            // no configuration needed
        }

        @Nullable
        @Override
        public Document resolve(@NonNull Conflict conflict) { return conflict.getRemoteDocument(); }
    }

    private static class DeleteResolver implements ConfigurableConflictResolver {
        @Override
        public void configure(@Nullable TypedMap config) {
            // no configuration needed
        }

        @Nullable
        @Override
        public Document resolve(@NonNull Conflict conflict) { return null; }
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
        public Document resolve(@NonNull Conflict conflict) {
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

    private static final Set<String> LEGAL_CREATE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_CONFIG);
        l.add(KEY_RESET);
        LEGAL_CREATE_KEYS = Collections.unmodifiableSet(l);
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
        l.add(KEY_PINNED_CERT);
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
        l.add(KEY_CONFLICT_RESOLVER);
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

    private static final Map<String, Supplier<ConfigurableConflictResolver>> CONFLICT_RESOLVER_FACTORIES;
    static {
        final Map<String, Supplier<ConfigurableConflictResolver>> m = new HashMap<>();
        m.put("local-wins", LocalWinsResolver::new);
        m.put("remote-wins", RemoteWinsResolver::new);
        m.put("delete", DeleteResolver::new);
        m.put("merge", MergeResolver::new);
        CONFLICT_RESOLVER_FACTORIES = Collections.unmodifiableMap(m);
    }

    @NonNull
    private final ReplicatorService replSvc;

    public ReplicatorManager(@NonNull DatabaseService dbSvc, @NonNull ReplicatorService replSvc) {
        super(dbSvc);
        this.replSvc = replSvc;
    }

    @SuppressFBWarnings("NP_NULL_ON_SOME_PATH_FROM_RETURN_VALUE")
    @NonNull
    public Map<String, Object> createRepl(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_CREATE_KEYS);

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

    @NonNull
    public Map<String, Object> getReplStatus(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_REPL_ID_KEYS);

        final String replId = req.getString(KEY_REPL_ID);
        if (replId == null) { throw new ClientError("Replicator id not specified"); }

        final ReplicatorStatus replStatus = replSvc.getReplStatus(ctxt, replId);
        Log.p(TAG, "Replicator status: " + replStatus);

        final List<DocumentReplication> docs = replSvc.getReplicatedDocs(ctxt, replId);
        return parseReplStatus(replStatus, docs);
    }

    @NonNull
    public Map<String, Object> stopRepl(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_REPL_ID_KEYS);

        final String replId = req.getString(KEY_REPL_ID);
        if (replId == null) { throw new ClientError("Replicator id not specified in stopReplicator"); }

        replSvc.stopRepl(ctxt, replId);

        return Collections.emptyMap();
    }

    @SuppressWarnings({"deprecation", "PMD.NPathComplexity"})
    @NonNull
    private ReplicatorConfiguration buildConfig(@NonNull TestContext ctxt, @NonNull TypedMap config) {
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
        if (collections == null || collections.isEmpty()) {
            throw new ClientError("Replicator configuration doesn't specify a list of collections");
        }

        final Database db = dbSvc.getOpenDb(ctxt, dbName);

        final ReplicatorConfiguration replConfig = new ReplicatorConfiguration(
                addCollections(
                        db,
                        collections,
                        ctxt), endpoint);

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

        final String pinnedCert = config.getString(KEY_PINNED_CERT);
        if (pinnedCert != null) { replConfig.setPinnedServerX509Certificate(str2X509Cert(pinnedCert)); }

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
                    throw new ClientError("Unrecognized authenticator type: " + authType);
            }
        }

        Log.p(TAG, "Build config: " + replConfig);
        return replConfig;
    }

    @SuppressWarnings("checkstyle:FinalLocalVariable")
    @NonNull
    private Set<CollectionConfiguration> addCollections(
        @NonNull Database db,
        @NonNull TypedList spec,
        @NonNull TestContext ctxt
    ) {
        Set<CollectionConfiguration> collectionConfigurations = new HashSet<>();
        for (int i = 0; i < spec.size(); i++) {
            final TypedMap replCollection = spec.getMap(i);
            if (replCollection == null) { throw new ClientError("Replication collection spec is null: " + i); }
            replCollection.validate(LEGAL_COLLECTION_KEYS);

            final TypedList collectionNames = replCollection.getList(KEY_NAMES);
            if (collectionNames == null) { throw new ClientError("no collections specified"); }
            Set<Collection> collections = dbSvc.getCollections(ctxt, db, collectionNames);
            for (Collection collection : collections) {
                collectionConfigurations.add(buildCollectionConfig(replCollection, collection));
            }
        }
        return collectionConfigurations;
    }

    @NonNull
    private CollectionConfiguration buildCollectionConfig(@NonNull TypedMap spec, @NonNull Collection collection) {
        final CollectionConfiguration collectionConfig = new CollectionConfiguration(collection);

        final List<String> channels = getList(spec.getList(KEY_CHANNELS));
        if (channels != null) { collectionConfig.setChannels(channels); }

        final List<String> docIds = getList(spec.getList(KEY_DOCUMENT_IDS));
        if (docIds != null) { collectionConfig.setDocumentIDs(docIds); }

        final TypedMap pushFilter = spec.getMap(KEY_PUSH_FILTER);
        if (pushFilter != null) { collectionConfig.setPushFilter(buildReplicatorFilter(pushFilter)); }

        final TypedMap pullFilter = spec.getMap(KEY_PULL_FILTER);
        if (pullFilter != null) { collectionConfig.setPullFilter(buildReplicatorFilter(pullFilter)); }

        final TypedMap conflictResolver = spec.getMap(KEY_CONFLICT_RESOLVER);
        if (conflictResolver != null) { collectionConfig.setConflictResolver(buildConflictResolver(conflictResolver)); }

        return collectionConfig;
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

    @NonNull
    private ConflictResolver buildConflictResolver(@NonNull TypedMap spec) {
        final String name = spec.getString(KEY_NAME);
        if (name == null) { throw new ClientError("No name specified for the conflict resolver"); }

        final Supplier<ConfigurableConflictResolver> resolverFactory
            = CONFLICT_RESOLVER_FACTORIES.get(name.toLowerCase(Locale.US).trim());
        if (resolverFactory == null) { throw new ClientError("Unrecognized conflict resolver: " + name); }

        final ConfigurableConflictResolver resolver = resolverFactory.get();
        resolver.configure(spec.getMap(KEY_PARAMS));

        return resolver;
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

    @NonNull
    private X509Certificate str2X509Cert(@NonNull String certificate) {
        try (InputStream certStream = new ByteArrayInputStream(certificate.getBytes(StandardCharsets.UTF_8))) {
            return (X509Certificate) CertificateFactory.getInstance("X509").generateCertificate(certStream);
        }
        catch (java.security.cert.CertificateException | IOException e) {
            throw new ClientError("Could not decode the certificate", e);
        }
    }
}
