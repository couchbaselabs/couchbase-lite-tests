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

import com.couchbase.lite.mobiletest.factories.RequestBuilder
import com.couchbase.lite.mobiletest.json.JsonEach
import com.couchbase.lite.mobiletest.json.CompareJsonObject
import com.couchbase.lite.mobiletest.json.UpdateJsonObject
import com.couchbase.lite.mobiletest.json.PrintJson
import com.couchbase.lite.mobiletest.json.JsonReduce
import com.couchbase.lite.mobiletest.factories.ReplyBuilder

import org.json.JSONObject
import org.junit.Assert
import org.junit.Test

class JsonTest : BaseTest() {

    @Test
    fun testJson2Args() {
        val data: MutableMap<String, Any?> = mutableMapOf("red" to null)
        data["green"] = listOf(true, "string", 43, 44L, 2.71828F, 2.71828)

        val reply = ReplyBuilder().buildReply(data)
        val request = RequestBuilder().buildRequest(reply.inputStream())

        Assert.assertNull(request.getString("red"))

        val list = request.getList("green")!!
        Assert.assertTrue(list.getBoolean(0)!!)
        Assert.assertEquals("string", list.getString(1))
        Assert.assertEquals(43L, list.getLong(2)) // the parser does this..
        Assert.assertEquals(44L, list.getLong(3))
        Assert.assertEquals(2.71828, list.getDouble(4)) // the parser does this..
        Assert.assertEquals(2.71828, list.getDouble(5))
    }

    @Test
    fun testJsonPrinter() {
        val json = JSONObject(
            """
                {
                    "name": "Alice",
                    "age": 20,
                    "address": {
                        "streetAddress": "100 Wall Street",
                        "city": "New York"
                    },
                    "phoneNumber": [
                        {
                            "type": "home",
                            "number": "212-333-1111"
                        },{
                            "type": "fax",
                            "number": "646-444-2222"
                        }
                    ],
                    gender: null
                }
            """.trimIndent()
        )

        JsonEach().forEach(json, PrintJson(""))
    }

    @Test
    fun testJsonIdentity() {
        val json1 = JSONObject(
            """
                {
                    "name": "Alice",
                    "age": 20,
                    "address": {
                        "streetAddress": "100 Wall Street",
                        "city": "New York"
                    },
                    "phoneNumber": [
                        {
                            "type": "home",
                            "number": "212-333-1111"
                        },{
                            "type": "fax",
                            "number": "646-444-2222"
                        }
                    ],
                    gender: null
                }
            """.trimIndent()
        )

        val json2 = JSONObject(
            """
                {
                    "name": "Alice",
                    "age": 20,
                    "address": {
                        "streetAddress": "100 Wall Street",
                        "city": "New York"
                    },
                    "phoneNumber": [
                        {
                            "type": "home",
                            "number": "212-333-1111"
                        },{
                            "type": "fax",
                            "number": "646-444-2222"
                        }
                    ],
                    gender: null
                }
            """.trimIndent()
        )

        Assert.assertTrue(JsonReduce<Boolean>().reduce(json1, CompareJsonObject(json2), true))
    }

    @Test
    fun testJsonUpdate() {

        val json1 = JSONObject(
            """
                {
                    "name": "Alice",
                    "age": 20,
                    "address": {
                        "streetAddress": "100 Wall Street",
                        "city": "New York"
                    },
                    "phoneNumber": [
                        {
                            "type": "home",
                            "number": "212-333-1111"
                        },{
                            "type": "fax",
                            "number": "646-444-2222"
                        }
                    ],
                    gender: null
                }
            """.trimIndent()
        )

        val json2 = JSONObject(
            """
                {
                    "address": {
                        "streetAddress": "140 E. Seventh St."
                    },
                    gender: "F"
                }
            """.trimIndent()
        )

        val json3 = JSONObject(
            """
                {
                    "name": "Alice",
                    "age": 20,
                    "address": {
                        "streetAddress": "140 E. Seventh St.",
                        "city": "New York"
                    },
                    "phoneNumber": [
                        {
                            "type": "home",
                            "number": "212-333-1111"
                        },{
                            "type": "fax",
                            "number": "646-444-2222"
                        }
                    ],
                    gender: "F"
                }
            """.trimIndent()
        )

        JsonEach().forEach(json2, UpdateJsonObject(json1))

        JsonEach().forEach(json1, PrintJson(""))

        Assert.assertTrue(JsonReduce<Boolean>().reduce(json1, CompareJsonObject(json3), true))
    }
}
