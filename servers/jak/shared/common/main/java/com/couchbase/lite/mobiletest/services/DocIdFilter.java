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

import java.util.EnumSet;
import java.util.Set;

import com.couchbase.lite.Collection;
import com.couchbase.lite.Document;
import com.couchbase.lite.DocumentFlag;
import com.couchbase.lite.ReplicationFilter;
import com.couchbase.lite.Scope;


public class DocIdFilter implements ReplicationFilter {
    public static final String DOT = ".";

    @NonNull
    final Set<String> permittedDocs;

    public DocIdFilter(@NonNull Set<String> docs) { permittedDocs = docs; }

    @Override
    public boolean filtered(@NonNull Document document, @NonNull EnumSet<DocumentFlag> ignore) {
        final Collection collection = document.getCollection();
        return permittedDocs.contains(
            ((collection == null) ? Scope.DEFAULT_NAME : collection.getScope().getName())
                + DOT
                + ((collection == null) ? Collection.DEFAULT_NAME : collection.getName())
                + DOT
                + document.getId());
    }
}
