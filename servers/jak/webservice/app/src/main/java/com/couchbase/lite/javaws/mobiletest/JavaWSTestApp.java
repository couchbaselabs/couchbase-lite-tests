package com.couchbase.lite.javaws.mobiletest;

import androidx.annotation.NonNull;

import com.couchbase.lite.mobiletest.BaseTestApp;


public class JavaWSTestApp extends BaseTestApp {
    @NonNull
    @Override
    public String getPlatform() { return "java-webservice"; }
}
