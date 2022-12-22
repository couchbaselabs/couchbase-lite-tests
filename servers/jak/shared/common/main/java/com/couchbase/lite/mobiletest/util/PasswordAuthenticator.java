package com.couchbase.lite.mobiletest.util;

import java.util.Arrays;

import com.couchbase.lite.ListenerPasswordAuthenticatorDelegate;


public class PasswordAuthenticator implements ListenerPasswordAuthenticatorDelegate {
    public boolean authenticate(String username, char[] password) {
        return ("testkit".equals(username)) && Arrays.equals(password, "pass".toCharArray());
    }
}
