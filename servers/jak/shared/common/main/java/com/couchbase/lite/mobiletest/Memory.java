package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;


// Not thread safe...
public final class Memory extends ObjectStore {
    public static final String PREFIX_REF = "@";

    public static class Ref {
        public final String key;

        public Ref(@NonNull String key) { this.key = key; }

        @Nullable
        public <T> T lookup(@NonNull Memory mem, @NonNull Class<T> type) { return mem.get(key, type); }
    }

    private static final Map<String, Map<String, Object>> SYM_TABS = new HashMap<>();

    @NonNull
    public static Memory get(@NonNull String client) {
        Map<String, Object> symTab = SYM_TABS.get(client);
        if (symTab == null) {
            symTab = new HashMap<>();
            SYM_TABS.put(client, symTab);
        }

        final TestApp app = TestApp.getApp();

        return new Memory(symTab, client, "_" + app.getPlatform() + "_" + app.getAppId());
    }

    public static void reset(@NonNull Memory mem) { SYM_TABS.remove(mem.client); }


    private final Map<String, Object> symTab;

    private final String client;
    private final String identifierSuffix;

    private final AtomicInteger nextAddress = new AtomicInteger(0);

    private Memory(@NonNull Map<String, Object> symTab, @NonNull String client, @NonNull String suffix) {
        super(symTab);
        this.symTab = symTab;
        this.client = client;
        identifierSuffix = suffix;
    }

    public void put(@NonNull String key, @NonNull Object value) { symTab.put(key, value); }

    public void addToList(@NonNull String key, @NonNull Object value) {
        List<Object> list = getList(key);
        if (list == null) { list = new ArrayList<>(); }
        list.add(value);
        put(key, list);
    }

    @NonNull
    public Ref addRef(@NonNull Object value) {
        final String address = "@" + nextAddress.getAndIncrement() + identifierSuffix;
        symTab.put(address, value);
        return new Ref(address);
    }

    public void removeRef(@NonNull Ref ref) { symTab.remove(ref.key); }

    @Nullable
    @Override
    protected <T> T get(@NonNull String name, @NonNull Class<T> expectedType) { return super.get(name, expectedType); }
}
