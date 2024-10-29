//
// Copyright (c) 2024 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.mobiletest.util;

import androidx.annotation.NonNull;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.mobiletest.services.Log;


public class DefaultLogger extends Log.TestLogger {

    @Override
    public void log(@NonNull LogLevel level, @NonNull LogDomain domain, @NonNull String message) {
        // these CBL messages have already been sent to the console
    }

    @Override
    public void close() {
        // no-op
    }

    // These are messages from the Test Server: log them to the console
    @Override
    public void log(LogLevel level, String tag, String msg, Exception err) {
        switch (level) {
            case DEBUG:
                android.util.Log.d(LOG_PREFIX + tag, msg, err);
                break;
            case VERBOSE:
                android.util.Log.v(LOG_PREFIX + tag, msg, err);
                break;
            case INFO:
                android.util.Log.i(LOG_PREFIX + tag, msg, err);
                break;
            case WARNING:
                android.util.Log.w(LOG_PREFIX + tag, msg, err);
                break;
            case ERROR:
                android.util.Log.e(LOG_PREFIX + tag, msg, err);
                break;
        }
    }
}
