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
package com.couchbase.lite.mobiletest

import com.couchbase.lite.mobiletest.util.CliUtils
import com.couchbase.lite.mobiletest.util.NetUtils
import org.junit.Assert
import org.junit.Test


class CliUtilsTest {
    @Test
    fun testNoArgs() {
        Assert.assertEquals(NetUtils.DEFAULT_PORT, CliUtils.getPort(arrayOf()))
    }

    @Test
    fun testPort() {
        Assert.assertEquals(9090, CliUtils.getPort(arrayOf("--port", "9090")))
    }

    // The desktop jar is launched as "java -jar <jar> server": unknown args are ignored.
    @Test
    fun testPortAfterOtherArgs() {
        Assert.assertEquals(9090, CliUtils.getPort(arrayOf("server", "--port", "9090")))
        Assert.assertEquals(NetUtils.DEFAULT_PORT, CliUtils.getPort(arrayOf("server")))
    }

    @Test
    fun testBoundaryPorts() {
        Assert.assertEquals(1, CliUtils.getPort(arrayOf("--port", "1")))
        Assert.assertEquals(65535, CliUtils.getPort(arrayOf("--port", "65535")))
    }

    @Test(expected = IllegalArgumentException::class)
    fun testMissingValue() {
        CliUtils.getPort(arrayOf("--port"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun testNotANumber() {
        CliUtils.getPort(arrayOf("--port", "abc"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun testTrailingJunk() {
        CliUtils.getPort(arrayOf("--port", "8080x"))
    }

    // 0 means "any free port" to the OS, but every consumer of this server needs a known port.
    @Test(expected = IllegalArgumentException::class)
    fun testZeroPort() {
        CliUtils.getPort(arrayOf("--port", "0"))
    }

    @Test(expected = IllegalArgumentException::class)
    fun testPortTooLarge() {
        CliUtils.getPort(arrayOf("--port", "70000"))
    }
}
