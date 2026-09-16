//
// Copyright (c) 2025 Couchbase, Inc All rights reserved.
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


public final class CliUtils {
    private CliUtils() { }

    private static final String ARG_PORT = "--port";

    private static final int MIN_PORT = 1;
    private static final int MAX_PORT = 65535;

    /**
     * Get the port to listen on from the command line arguments: "--port &lt;port&gt;".
     * Arguments that are not recognized are ignored: the variants are launched with
     * positional arguments of their own (the desktop jar with "server", prunsrv with
     * "start") and a daemon container may add more.
     *
     * @param args the command line arguments
     * @return the requested port, or NetUtils.DEFAULT_PORT if --port was not specified
     * @throws IllegalArgumentException if --port has a missing or unusable value
     */
    public static int getPort(@NonNull String[] args) {
        for (int i = 0; i < args.length; i++) {
            if (!ARG_PORT.equals(args[i])) { continue; }
            if (i + 1 >= args.length) { throw new IllegalArgumentException("Missing value for " + ARG_PORT); }
            return parsePort(args[i + 1]);
        }
        return NetUtils.DEFAULT_PORT;
    }

    private static int parsePort(@NonNull String val) {
        int port = -1;
        try { port = Integer.parseInt(val); }
        catch (NumberFormatException ignore) { }

        if ((port < MIN_PORT) || (port > MAX_PORT)) {
            throw new IllegalArgumentException(
                "Invalid " + ARG_PORT + " value: \"" + val + "\" (expected an integer in "
                    + MIN_PORT + ".." + MAX_PORT + ")");
        }

        return port;
    }
}
