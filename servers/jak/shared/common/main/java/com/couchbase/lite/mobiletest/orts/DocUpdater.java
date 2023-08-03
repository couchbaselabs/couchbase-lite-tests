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
package com.couchbase.lite.mobiletest.orts;

import androidx.annotation.NonNull;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.couchbase.lite.Document;
import com.couchbase.lite.MutableDocument;
import com.couchbase.lite.mobiletest.data.TreeEach;
import com.couchbase.lite.mobiletest.data.TypedMap;


public class DocUpdater {

    //    For each property in updatedProperties do the following:
    //    If the value is not a dictionary, set the value and move on
    //    If the value is a dictionary, check the existing value
    //    If the existing value is not a dictionary, set the value and move on
    //    Start iterating the new value keys
    //    If the key doesn't already exist in the existing value, add the value and move on
    //    If the key exists already, check the value to be set, and go to step 1
    private static class MapUpdater implements TreeEach.MapOp {
        private final Map<String, Object> target;

        MapUpdater(@NonNull Map<String, Object> target) { this.target = target; }

        @SuppressWarnings("unchecked")
        @NonNull
        @Override
        public TreeEach.MapOp startMap(@NonNull String key) {
            final Map<String, Object> val;

            final Object oldValue = target.get(key);
            if (oldValue instanceof Map) { val = (Map<String, Object>) oldValue; }
            else {
                val = new HashMap<>();
                target.put(key, val);
            }

            return new MapUpdater(val);
        }

        @SuppressWarnings("unchecked")
        @NonNull
        @Override
        public TreeEach.ListOp startList(@NonNull String key) {
            final List<Object> val;

            final Object oldValue = target.get(key);
            if (oldValue instanceof List) { val = (List<Object>) oldValue; }
            else {
                val = new ArrayList<>();
                target.put(key, val);
            }

            return new ListUpdater(val);
        }

        @Override
        public void strVal(@NonNull String key, @NonNull String str) { target.put(key, str); }

        @Override
        public void numVal(@NonNull String key, @NonNull Double num) { target.put(key, num); }

        @Override
        public void numVal(@NonNull String key, @NonNull Float num) { target.put(key, num); }

        @Override
        public void numVal(@NonNull String key, @NonNull Long num) { target.put(key, num); }

        @Override
        public void numVal(@NonNull String key, @NonNull Integer num) { target.put(key, num); }

        @Override
        public void boolVal(@NonNull String key, @NonNull Boolean bool) { target.put(key, bool); }

        @Override
        public void nullVal(@NonNull String key) { target.put(key, null); }

        @Override
        public void endMap() {
            // This method is intentionally left blank
        }
    }

    // As it stands, this will replace an element from the source with the corresponding element
    // from the updates unless both source and update are of the same type, and either map or list.
    // In those two cases, the source gets copied to the target.  Then, of course, the recursive
    // call manipulates the contents of the map/list.  That works as expected from maps.  For a
    // list, though, it will completely replace elements in the source with any corresponding
    // elements in the update.
    public static class ListUpdater implements TreeEach.ListOp {
        private final List<Object> target;

        public ListUpdater(@NonNull List<Object> target) { this.target = target; }

        @SuppressWarnings("unchecked")
        @NonNull
        @Override
        public TreeEach.MapOp startMap(int idx) {
            final Map<String, Object> val;

            final boolean adding = idx >= target.size();
            final Object oldValue = adding ? null : target.get(idx);
            if (oldValue instanceof Map) { val = (Map<String, Object>) oldValue; }
            else {
                val = new HashMap<>();
                if (adding) { target.add(idx, val); }
                else { target.set(idx, val); }
            }

            return new MapUpdater(val);
        }

        @SuppressWarnings("unchecked")
        @NonNull
        @Override
        public TreeEach.ListOp startList(int idx) {
            final List<Object> val;

            final Object oldValue = (idx >= target.size()) ? null : target.get(idx);
            if (oldValue instanceof List) { val = (List<Object>) oldValue; }
            else {
                val = new ArrayList<>();
                update(idx, val);
            }

            return new ListUpdater(val);
        }

        @Override
        public void strVal(int idx, @NonNull String str) { update(idx, str); }

        @Override
        public void numVal(int idx, @NonNull Double num) { update(idx, num); }

        @Override
        public void numVal(int idx, @NonNull Float num) { update(idx, num); }

        @Override
        public void numVal(int idx, @NonNull Long num) { update(idx, num); }

        @Override
        public void numVal(int idx, @NonNull Integer num) { update(idx, num); }

        @Override
        public void boolVal(int idx, @NonNull Boolean bool) { update(idx, bool); }

        @Override
        public void nullVal(int idx) { update(idx, null); }

        @Override
        public void endList() {
            // This method is intentionally left blank
        }

        private void update(int idx, Object val) {
            while (idx >= target.size()) { target.add(null); }
            target.set(idx, val);
        }
    }


    @NonNull
    private final Document doc;

    public DocUpdater(@NonNull Document doc) { this.doc = doc; }

    // Note that the method id destructive: it may change the src
    @NonNull
    public MutableDocument update(@NonNull TypedMap src) {
        final Map<String, Object> data = doc.toMap();

        new TreeEach().forEach(src, new MapUpdater(data));

        return doc.toMutable().setData(data);
    }
}

