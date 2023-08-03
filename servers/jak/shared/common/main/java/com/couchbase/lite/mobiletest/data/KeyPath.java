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
package com.couchbase.lite.mobiletest.data;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.couchbase.lite.mobiletest.errors.ClientError;


public class KeyPath {
    public abstract static class PathElem<T> {
        private abstract static class Ref<P, R> {
            @NonNull
            protected final P p;
            @NonNull
            protected final R r;

            Ref(@NonNull P p, @NonNull R r) {
                this.p = p;
                this.r = r;
            }

            abstract void backfill(@NonNull Object val);
        }

        public static class Property extends PathElem<String> {
            static class MapRef extends Ref<Map<String, Object>, String> {
                MapRef(@NonNull Map<String, Object> map, @NonNull String s) { super(map, s); }

                @Override
                public void backfill(@NonNull Object val) { p.put(r, val); }
            }


            Property(@NonNull String prop) { super(prop); }

            @Nullable
            @Override
            public Object next(@Nullable Object node) {
                final Map<String, Object> m = getTarget(node);

                if (m.containsKey(elem)) { return m.get(elem); }

                final MapRef r = new MapRef(m, elem);
                m.put(elem, r);

                return r;
            }

            @Override
            public void set(@Nullable Object node, @Nullable Object val) { getTarget(node).put(elem, val); }

            @Override
            public void delete(@Nullable Object node) { getTarget(node).remove(elem); }

            @SuppressWarnings("unchecked")
            @NonNull
            private Map<String, Object> getTarget(@Nullable Object node) {
                if (node instanceof Map) { return (Map<String, Object>) node; }

                if (node instanceof Ref) {
                    final Ref<?, ?> r = (Ref<?, ?>) node;
                    final Map<String, Object> m = new HashMap<>();
                    r.backfill(m);
                    return m;
                }

                throw new ClientError("Cannot apply property " + elem + " to " + node);
            }
        }

        public static class Index extends PathElem<Integer> {
            static class ListRef extends Ref<List<Object>, Integer> {
                ListRef(@NonNull List<Object> objects, @NonNull Integer integer) { super(objects, integer); }
                @Override
                public void backfill(@NonNull Object val) { p.set(r, val); }
            }


            Index(@NonNull Integer idx) { super(idx); }

            @Nullable
            @Override
            public Object next(@Nullable Object node) {
                final List<Object> l = getTarget(node);

                final int n = l.size();
                if (n > elem) { return l.get(elem); }

                for (int i = n; i < elem; i++) { l.add(null); }
                final ListRef r = new ListRef(l, elem);
                l.add(r);

                return r;
            }

            @Override
            public void set(@Nullable Object node, @Nullable Object val) {
                final List<Object> l = getTarget(node);
                for (int i = l.size(); i <= elem; i++) { l.add(null); }
                l.set(elem, val);
            }

            @Override
            public void delete(@Nullable Object node) {
                final List<Object> l = getTarget(node);
                if (l.size() > elem) { l.remove(elem); }
            }

            @NonNull
            @SuppressWarnings("unchecked")
            private List<Object> getTarget(@Nullable Object node) {
                if (node instanceof List) { return (List<Object>) node; }

                if (node instanceof Ref) {
                    final Ref<?, ?> r = (Ref<?, ?>) node;
                    final List<Object> l = new ArrayList<>();
                    r.backfill(l);
                    return l;
                }

                throw new ClientError("Cannot apply index " + elem + " to " + node);
            }
        }


        @NonNull
        protected final T elem;

        private PathElem(@NonNull T elem) { this.elem = elem; }

        @Nullable
        public abstract Object next(@Nullable Object node);
        public abstract void set(@Nullable Object node, @Nullable Object val);
        public abstract void delete(@Nullable Object node);
    }


    @NonNull
    private final List<PathElem<?>> path = new ArrayList<>();

    public int size() { return path.size(); }

    public void addElement(PathElem<?> elem) { path.add(elem); }

    @Nullable
    public Object get(@NonNull Map<String, Object> root) {
        Object val = root;
        for (PathElem<?> elem: path) { val = elem.next(val); }
        return val;
    }

    public void set(@NonNull Map<String, Object> root, @Nullable Object newVal) {
        final int n = path.size() - 1;
        Object val = root;
        for (PathElem<?> elem: path.subList(0, n)) { val = elem.next(val); }
        path.get(n).set(val, newVal);
    }

    public void delete(@NonNull Map<String, Object> root) {
        final int n = path.size() - 1;
        Object val = root;
        for (PathElem<?> elem: path.subList(0, n)) { val = elem.next(val); }
        path.get(n).delete(val);
    }
}
