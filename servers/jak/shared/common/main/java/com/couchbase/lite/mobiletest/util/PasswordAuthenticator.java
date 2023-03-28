package com.couchbase.lite.mobiletest.util;

import androidx.annotation.NonNull;

import java.util.Arrays;

import com.couchbase.lite.ListenerPasswordAuthenticatorDelegate;


public class PasswordAuthenticator implements ListenerPasswordAuthenticatorDelegate {
    public boolean authenticate(@NonNull String username, @NonNull char[] password) {
        return ("testkit".equals(username)) && Arrays.equals(password, "pass".toCharArray());
    }
}
