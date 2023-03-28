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
package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.HashMap;
import java.util.Map;


public class TestException extends RuntimeException {
    public static final int TESTSERVER = 0;
    public static final int CBL = 1;
    public static final int POSIX = 2;
    public static final int SQLITE = 3;
    public static final int FLEECE = 4;
    public static final int NETWORK = 5;
    public static final int WEBSOCKET = 6;

    @NonNull
    public static String printError(@NonNull Exception e) {
        final StringWriter sw = new StringWriter();
        sw.write(e.getLocalizedMessage());
        sw.write("\n");
        final PrintWriter pw = new PrintWriter(sw);
        e.printStackTrace(pw);
        return pw.toString();
    }


    private final int domain;
    private final int code;

    public TestException(int domain, int code) { this(domain, code, null, null); }

    public TestException(int domain, int code, @Nullable String message) { this(domain, code, message, null); }

    public TestException(int domain, int code, @Nullable String message, @Nullable Exception e) {
        super(message, e);
        this.domain = domain;
        this.code = code;
    }

    @NonNull
    public Map<String, Object> getError() {
        final Map<String, Object> content = new HashMap<>();
        content.put("domain", domain);
        content.put("code", code);
        content.put("message", getLocalizedMessage());
        return content;
    }
}
