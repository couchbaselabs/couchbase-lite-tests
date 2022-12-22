package com.couchbase.lite.javaws.mobiletest;

import androidx.annotation.NonNull;

import com.couchbase.lite.mobiletest.BaseTestApp;


public class JavaWSTestKitApp extends BaseTestApp {
    private final String containerName;

    public JavaWSTestKitApp(@NonNull String containerName) { this.containerName = containerName; }

    @NonNull
    @Override
    public String getPlatform() { return "java-webservice"; }

    @NonNull
    @Override
    public String getAppId() { return containerName; }
}
