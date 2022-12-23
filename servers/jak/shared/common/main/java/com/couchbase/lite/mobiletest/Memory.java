package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;


public final class Memory extends ObjectStore {
    public static class Ref {
        public final String key;

        public Ref(@NonNull String key) { this.key = key; }

        @Nullable
        public <T> T lookup(@NonNull Memory mem, @NonNull Class<T> type) { return mem.get(key, type); }
    }

    private final String id;
    private final String platform;

    private final Map<String, Object> symTab;
    private final AtomicInteger nextAddress = new AtomicInteger(0);

    @NonNull
    public static Memory create(@NonNull String id) { return new Memory(id, new HashMap<>()); }


    private Memory(@NonNull String id, @NonNull Map<String, Object> symTab) {
        super(symTab);
        this.id = id;
        this.symTab = symTab;
        platform = TestApp.getApp().getPlatform();
    }

    @NonNull
    public Ref add(@NonNull Object value) {
        final String address = "@" + nextAddress.getAndIncrement() + "_" + id + "_" + platform;
        synchronized (symTab) { symTab.put(address, value); }
        return new Ref(address);
    }

    public void remove(@NonNull Ref ref) {
        synchronized (symTab) { symTab.remove(ref.key); }
    }

    public void remove(@NonNull String address) {
        synchronized (symTab) { symTab.remove(address); }
    }

    public void flush() {
        synchronized (symTab) { symTab.clear(); }
        nextAddress.set(0);
    }

    @Nullable
    @Override
    protected <T> T get(@NonNull String name, @NonNull Class<T> expectedType) {
        synchronized (symTab) { return super.get(name, expectedType); }
    }
}
