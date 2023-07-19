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

import com.couchbase.lite.mobiletest.errors.ClientError
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
            1,
            Dispatcher.Method.GET,
            "/",
            ByteArrayInputStream("{}".toByteArray())
        ).use { r ->
            Assert.assertNotNull(r)

            resp = Moshi.Builder().build().adapter(Any::class.java)
                .fromJson(r.content.source().buffer()) as? Map<String, Any>
        }

        Assert.assertEquals("CouchbaseLite ", (resp?.get("version") as? String)?.substring(0, 14))
    }

    @Test
    fun testBadRequestVersion() {
        try {
            TestApp.getApp().dispatcher.handleRequest(
                "testing",
                97,
                Dispatcher.Method.GET,
                "foo",
                ByteArrayInputStream("{}".toByteArray())
            )
        }
        catch (err: ClientError) {
            val msg = err.message
            Assert.assertTrue(msg?.startsWith("Unrecognized request") ?: false)
            Assert.assertTrue(msg?.contains("@97") ?: false)
        }
    }

    @Test
    fun testBadRequestMethod() {
        try {
            TestApp.getApp().dispatcher.handleRequest(
                "testClient",
                1,
                Dispatcher.Method.PUT,
                "/",
                ByteArrayInputStream("{}".toByteArray())
            )
        }
        catch (err: ClientError) {
            val msg = err.message
            Assert.assertTrue(msg?.startsWith("Unrecognized request") ?: false)
            Assert.assertTrue(msg?.contains(" PUT ") ?: false)
        }
    }

    @Test
    fun testBadRequestEndpoint() {
        try {
            TestApp.getApp().dispatcher.handleRequest(
                "testing",
                1,
                Dispatcher.Method.GET,
                "/foo",
                ByteArrayInputStream("{}".toByteArray())
            )
        }
        catch (err: ClientError) {
            val msg = err.message
            Assert.assertTrue(msg?.startsWith("Unrecognized request") ?: false)
            Assert.assertTrue(msg?.contains(" /foo ") ?: false)
        }
    }
}
