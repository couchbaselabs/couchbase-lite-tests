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

    public DefaultLogger(@NonNull LogLevel level, @NonNull LogDomain... domains) {
        super(level, domains);
    }

    @Override
    public void writeLog(LogLevel level, LogDomain tag, String msg) {
        switch (level) {
            case DEBUG:
                android.util.Log.d(LOG_PREFIX + tag, msg);
                break;
            case VERBOSE:
                android.util.Log.v(LOG_PREFIX + tag, msg);
                break;
            case INFO:
                android.util.Log.i(LOG_PREFIX + tag, msg);
                break;
            case WARNING:
                android.util.Log.w(LOG_PREFIX + tag, msg);
                break;
            case ERROR:
                android.util.Log.e(LOG_PREFIX + tag, msg);
                break;
        }
    }

    @Override
    public void close() {
        // no-op
    }

}
