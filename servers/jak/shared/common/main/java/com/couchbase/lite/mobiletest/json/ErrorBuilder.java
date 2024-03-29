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
package com.couchbase.lite.mobiletest.json;

import androidx.annotation.NonNull;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.HashMap;
import java.util.Map;

import com.couchbase.lite.mobiletest.errors.TestError;


public class ErrorBuilder {
    private static final String KEY_DOMAIN = "domain";
    private static final String KEY_CODE = "code";
    private static final String KEY_MESSAGE = "message";


    private final TestError error;

    public ErrorBuilder(@NonNull TestError error) { this.error = error; }

    @NonNull
    public Map<String, Object> build() {
        final StringWriter sw = new StringWriter();
        sw.write(error.getLocalizedMessage());
        sw.write("\n");
        final PrintWriter pw = new PrintWriter(sw);
        error.printStackTrace(pw);

        final Map<String, Object> json = new HashMap<>();
        json.put(KEY_DOMAIN, error.getDomain());
        json.put(KEY_CODE, error.getCode());
        json.put(KEY_MESSAGE, sw.toString().replace("\\", "\\\\").replace("\"", "\\"));

        return json;
    }
}
