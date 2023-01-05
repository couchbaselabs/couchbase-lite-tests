//
// Copyright (c) 2022 Couchbase, Inc All rights reserved.
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

import org.junit.Assert
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

class BasicTest : BaseTest() {
    @Test
    fun testGetVersion() {

        val r = TestApp.getApp().dispatcher.run(
            2,
            "testing",
            Dispatcher.Method.GET,
            "version",
            ByteArrayInputStream("{}".toByteArray()))

        Assert.assertNotNull(r)
        Assert.assertEquals("application/json", r.contentType)

        val out = ByteArrayOutputStream()
        val buffer = ByteArray(1024)
        while (true) {
            val n = r.data.read(buffer, 0, buffer.size)
            if (n <= 0) { break; }
            out.write(buffer, 0, n)
        }

        Assert.assertEquals("{\"version\":\"Test Server (", out.toString("UTF-8").substring(0, 25))
    }
}

