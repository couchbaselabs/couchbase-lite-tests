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

import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import com.couchbase.lite.CouchbaseLiteException;
import com.couchbase.lite.MaintenanceType;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.CblApiFailure;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.services.DatabaseService;
import com.couchbase.lite.mobiletest.trees.TypedMap;


public class PerformMaintenance {
    private static final String KEY_DATABASE = "database";
    private static final String KEY_MAINTENANCE_TYPE = "maintenanceType";
    private static final String TYPE_REINDEX = "reindex";
    private static final String TYPE_COMPACT = "compact";
    private static final String TYPE_INTEGRITY_CHECK = "integritycheck";
    private static final String TYPE_OPTIMIZE = "optimize";
    private static final String TYPE_FULL_OPTIMIZE = "fulloptimize";

    private static final Set<String> LEGAL_MANTENANCE_KEYS;
    static {
        final Set<String> l = new HashSet<>();
        l.add(KEY_DATABASE);
        l.add(KEY_MAINTENANCE_TYPE);
        LEGAL_MANTENANCE_KEYS = Collections.unmodifiableSet(l);
    }

    private static final Map<String, MaintenanceType> MANTENANCE_TYPES;
    static {
        final Map<String, MaintenanceType> m = new HashMap<>();
        m.put(TYPE_REINDEX, MaintenanceType.REINDEX);
        m.put(TYPE_COMPACT, MaintenanceType.COMPACT);
        m.put(TYPE_INTEGRITY_CHECK, MaintenanceType.INTEGRITY_CHECK);
        m.put(TYPE_OPTIMIZE, MaintenanceType.OPTIMIZE);
        m.put(TYPE_FULL_OPTIMIZE, MaintenanceType.FULL_OPTIMIZE);
        MANTENANCE_TYPES = Collections.unmodifiableMap(m);
    }

    @NonNull
    private final DatabaseService dbSvc;

    public PerformMaintenance(@NonNull DatabaseService dbSvc) { this.dbSvc = dbSvc; }

    @NonNull
    public final Map<String, Object> doMaintenance(@NonNull TestContext ctxt, @NonNull TypedMap req) {
        req.validate(LEGAL_MANTENANCE_KEYS);

        final String dbName = req.getString(KEY_DATABASE);
        if (dbName == null) { throw new ClientError("Perform maintenance request doesn't specify a database"); }

        final String type = req.getString(KEY_MAINTENANCE_TYPE);
        if (type == null) { throw new ClientError("Perform maintenance request doesn't specify a maintenance type"); }

        final MaintenanceType mt = MANTENANCE_TYPES.get(type.toLowerCase(Locale.getDefault()));
        if (mt == null) { throw new ClientError("Unrecognized maintenance type: " + type); }

        try { dbSvc.getOpenDb(ctxt, dbName).performMaintenance(mt); }
        catch (CouchbaseLiteException e) { throw new CblApiFailure("Failed running maintenance type: " + type, e); }

        return Collections.emptyMap();
    }
}

