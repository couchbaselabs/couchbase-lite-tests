package com.couchbase.lite.javadesktop.mobiletest;

import androidx.annotation.NonNull;

import com.couchbase.lite.mobiletest.BaseTestApp;


public class JavaDesktopTestApp extends BaseTestApp {

    @NonNull
    @Override
    public String getPlatform() { return "java-desktop"; }
}
