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
package com.couchbase.lite.mobiletest.tools;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.Map;

import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.mobiletest.data.TypedList;
import com.couchbase.lite.mobiletest.data.TypedMap;
import com.couchbase.lite.mobiletest.errors.ClientError;


public class DocUpdater {
    @NonNull
    private final MutableDocument mDoc;

    public DocUpdater(@NonNull MutableDocument mDoc) { this.mDoc = mDoc; }

    @NonNull
    public MutableDocument update(@Nullable TypedList updates) {
        if (updates == null) { return mDoc; }

        final int n = updates.size();
        if (n < 1) { return mDoc; }

        for (int i = 0; i < n; i++) {
            final TypedMap update = updates.getMap(i);
            if (update == null) { throw new ClientError("Empty update"); }
        }

        final Map<String, Object> data = mDoc.toMap();

        return new MutableDocument().setData(data);
    }
}
