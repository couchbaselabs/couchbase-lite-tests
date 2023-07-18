package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;


// Not thread safe...
public final class Memory extends TypedMap {
    public static final String PREFIX_REF = "@";

    public static class Ref {
        public final String key;

        public Ref(@NonNull String key) { this.key = key; }

        @Nullable
        public <T> T lookup(@NonNull Memory mem, @NonNull Class<T> type) { return mem.get(key, type); }
    }

    @NonNull
    private final String client;

    @NonNull
    private final Map<String, Object> symTab;

    @NonNull
    private final String identifierSuffix;

    @NonNull
    private final AtomicInteger nextAddress = new AtomicInteger(0);

    Memory(@NonNull String client, @NonNull Map<String, Object> symTab, @NonNull String suffix) {
        super(symTab);
        this.client = client;
        this.symTab = symTab;
        identifierSuffix = suffix;
    }

    @NonNull
    public String getClient() { return client; }

    @NonNull
    public Ref addRef(@NonNull Object value) {
        final String address = "@" + nextAddress.getAndIncrement() + identifierSuffix;
        symTab.put(address, value);
        return new Ref(address);
    }

    public void removeRef(@NonNull Ref ref) { symTab.remove(ref.key); }
}
