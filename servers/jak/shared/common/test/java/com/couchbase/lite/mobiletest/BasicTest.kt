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

import com.squareup.moshi.Moshi
import okio.buffer
import okio.source
import org.junit.Assert
import org.junit.Test
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream

class BasicTest : BaseTest() {
    @Suppress("UNCHECKED_CAST")
    @Test
    fun testGetVersion() {
        var resp: Map<String, Any>?

        TestApp.getApp().dispatcher.handleRequest(
            "testing",
            2,
            Dispatcher.Method.GET,
            "/",
            ByteArrayInputStream("{}".toByteArray())
        ).use { r ->
            Assert.assertNotNull(r)
            Assert.assertEquals(Reply.Status.OK, r.status)
            Assert.assertEquals("application/json", r.contentType)

            resp = Moshi.Builder().build().adapter(Any::class.java)
                .fromJson(r.content.source().buffer()) as? Map<String, Any>
        }

        Assert.assertEquals("CouchbaseLite ", (resp?.get("version") as? String)?.substring(0, 14))
    }

    @Test
    fun testBadRequest() {
        var resp: String

        TestApp.getApp().dispatcher.handleRequest(
            "testing",
            2,
            Dispatcher.Method.GET,
            "foo",
            ByteArrayInputStream("{}".toByteArray())
        ).use { r ->
            Assert.assertNotNull(r)
            Assert.assertEquals(Reply.Status.METHOD_NOT_ALLOWED, r.status)
            Assert.assertEquals("text/plain", r.contentType)

            ByteArrayOutputStream().use { out ->
                val buffer = ByteArray(1024)
                r.content.use {
                    while (true) {
                        val n = it.read(buffer, 0, buffer.size)
                        if (n <= 0) break
                        out.write(buffer, 0, n)
                    }
                }
                resp = out.toString("UTF-8")
            }
        }

        Assert.assertEquals("Unrecognized request: ", resp.substring(0, 22))
    }
}
