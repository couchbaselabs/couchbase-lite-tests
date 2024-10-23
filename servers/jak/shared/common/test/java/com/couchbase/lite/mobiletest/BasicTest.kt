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

class BasicTest : BaseTest() {
    @Suppress("UNCHECKED_CAST")
    @Test
    fun testGetVersion() {
        var resp: Map<String, Any>?

        GetDispatcher(TestApp.getApp()).handleRequest("testing", 1, "/").use { ctxt ->
            Assert.assertNotNull(ctxt)
            resp = Moshi.Builder().build().adapter(Any::class.java)
                .fromJson(ctxt.content.source().buffer()) as? Map<String, Any>
        }

        Assert.assertTrue(
            """Test Server \d+\.\d+\.\d+@[abcdef\d]+ on .+ using CouchbaseLite""".toRegex()
                .containsMatchIn(resp?.get("additionalInfo") as? String ?: "")
        )
    }

    @Test
    fun testBadRequestVersion() {
        try {
            PostDispatcher(TestApp.getApp()).handleRequest(
                "testing",
                97,
                "/reset",
                TestApp.CONTENT_TYPE_JSON,
                ByteArrayInputStream("{}".toByteArray())
            )
        } catch (err: ClientError) {
            Assert.assertTrue(
                """Unrecognized post request:.+/reset v97""".toRegex()
                    .containsMatchIn(err.message as String)
            )
        }
    }

    @Test
    fun testBadRequestEndpoint() {
        try {
            PostDispatcher(TestApp.getApp()).handleRequest(
                "testing",
                1,
                "/foo",
                TestApp.CONTENT_TYPE_JSON,
                ByteArrayInputStream("{}".toByteArray())
            )
        } catch (err: ClientError) {
            val msg = err.message
            Assert.assertTrue(msg?.startsWith("Unrecognized post request") ?: false)
            Assert.assertTrue(msg?.contains(" /foo ") ?: false)
        }
    }
}
