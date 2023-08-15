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
package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.List;

import com.couchbase.lite.DocumentReplication;
import com.couchbase.lite.DocumentReplicationListener;


public class DocReplListener implements DocumentReplicationListener {
    private List<DocumentReplication> replicatedDocs;

    @Override
    public void replication(@NonNull DocumentReplication replication) {
        synchronized (this) {
            if (replicatedDocs == null) { replicatedDocs = new ArrayList<>(); }
            replicatedDocs.add(replication);
        }
    }

    @Nullable
    public List<DocumentReplication> getReplicatedDocs() {
        final List<DocumentReplication> repls;
        synchronized (this) {
            repls = replicatedDocs;
            replicatedDocs = null;
        }
        return repls;
    }
}
