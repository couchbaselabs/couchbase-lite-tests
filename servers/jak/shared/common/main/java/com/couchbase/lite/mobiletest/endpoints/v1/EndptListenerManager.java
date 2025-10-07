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
package com.couchbase.lite.mobiletest.endpoints.v1;

import androidx.annotation.NonNull;

import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.Database;
import com.couchbase.lite.URLEndpointListener;
import com.couchbase.lite.URLEndpointListenerConfiguration;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.services.ListenerService;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.trees.TypedList;
import com.couchbase.lite.mobiletest.trees.TypedMap;


@SuppressFBWarnings("EI_EXPOSE_REP2")
public class EndptListenerManager {
    private static final String TAG = "LSTNR_MGR_V1";

    private static final String KEY_DATABASE = "database";
    private static final String KEY_COLLECTIONS = "collections";
    private static final String KEY_PORT = "port";
    private static final String KEY_ID = "id";

    private static final Set<String> LEGAL_CREATE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_COLLECTIONS);
        l.add(KEY_PORT);
        LEGAL_CREATE_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Set<String> LEGAL_STOP_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_ID);
        LEGAL_STOP_KEYS = Collections.unmodifiableSet(l);
    }


    @NonNull
    private final DatabaseService dbSvc;
    @NonNull
    private final ListenerService listenerSvc;

    public EndptListenerManager(@NonNull DatabaseService dbSvc, @NonNull ListenerService listenerSvc) {
        this.dbSvc = dbSvc;
        this.listenerSvc = listenerSvc;
    }

    @NonNull
    public Map<String, Object> startListener(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_CREATE_KEYS);

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Listener configuration doesn't specify a database"); }

        final TypedList collections = req.getList(KEY_COLLECTIONS);
        if (collections == null) {
            throw new ClientError("Listener configuration doesn't specify a list of collections");
        }

        if (collections.isEmpty()) { throw new ClientError("Listener configuration doesn't specify any collections"); }

        final Database db = dbSvc.getOpenDb(ctxt, dbName);
        final URLEndpointListenerConfiguration listenerConfig
            = new URLEndpointListenerConfiguration(dbSvc.getCollections(ctxt, db, collections));

        final Integer port = req.getInt(KEY_PORT);
        if (port != null) { listenerConfig.setPort(port); }

        final URLEndpointListener listener = new URLEndpointListener(listenerConfig);
        try { listener.start(); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed to start listener", e); }

        final String listenerId = listenerSvc.addListener(ctxt, listener);
        Log.p(TAG, "Started listener: " + listenerId);

        final int listenerPort = listener.getPort();
        if (listenerPort <= 0) { throw new CblApiFailure(new CouchbaseLiteException("Unable to get listener port")); }

        final Map<String, Object> ret = new HashMap<>();
        ret.put(KEY_ID, listenerId);
        ret.put(KEY_PORT, listenerPort);

        return ret;
    }

    @NonNull
    public Map<String, Object> stopListener(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_STOP_KEYS);

        final String listenerId = req.getString(KEY_ID);
        if (listenerId == null) { throw new ClientError("Listener id not specified in stopListener"); }

        listenerSvc.stopListener(ctxt, listenerId);

        return Collections.emptyMap();
    }
}
