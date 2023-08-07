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

import com.couchbase.lite.MutableArray
import com.couchbase.lite.MutableDictionary
import com.couchbase.lite.MutableDocument
import com.couchbase.lite.mobiletest.data.TreeEach
import com.couchbase.lite.mobiletest.orts.DocUpdater
import com.couchbase.lite.mobiletest.tools.PrintReq
import com.couchbase.lite.mobiletest.tools.ReplyBuilder
import com.couchbase.lite.mobiletest.tools.RequestBuilder
import org.junit.Assert
import org.junit.Test
import java.io.ByteArrayInputStream

class JsonTest : BaseTest() {

    @Test
    fun testJson2Args() {
        val data: MutableMap<String, Any?> = mutableMapOf("red" to null)
        data["green"] = listOf(true, "string", 43, 44L, 2.71828F, 2.71828)

        val reply = ReplyBuilder(data).buildReply()
        val request = RequestBuilder(reply.inputStream()).buildRequest()

        Assert.assertNull(request.getString("red"))

        val list = request.getList("green")!!
        Assert.assertTrue(list.getBoolean(0)!!)
        Assert.assertEquals("string", list.getString(1))
        Assert.assertEquals(43L, list.getLong(2)) // the parser does this
        Assert.assertEquals(44L, list.getLong(3))
        Assert.assertEquals(2.71828, list.getDouble(4)) // the parser does this
        Assert.assertEquals(2.71828, list.getDouble(5))
    }

    @Test
    fun testJsonPrinter() {
        val json = """
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
            """

        TreeEach().forEach(
            RequestBuilder(ByteArrayInputStream(json.trimIndent().toByteArray())).buildRequest(),
            PrintReq("")
        )
    }

    @Test
    fun testDocUpdater() {
        val address = MutableDictionary()
        address.setString("streetAddress", "140 E. Seventh St.")
        address.setString("city", "New York")

        val children = MutableArray()

        val child = MutableDictionary()
        child.setString("gender", "M")
        child.setInt("age", 12)
        children.addDictionary(child)

        // and empty spot for carol...
        children.addDictionary(MutableDictionary())

        val doc = MutableDocument()
        doc.setString("name", "Eve")
        doc.setString("gender", "F")
        doc.setArray("children", children)
        doc.setDictionary("address", address)

        val json = """
                {
                    "name": "Alice",
                    "age": 20,
                    "address": {
                        "streetAddress": "100 Wall Street",
                        "zip": 10118
                    },
                    "children": [
                        {
                            "name": "Bob",
                            "gender": "M",
                            "age": 13
                        },
                        {
                            "name": "Carol",
                            "gender": "F",
                            "age": 16.5
                        }
                    ]
                }
            """

        val newDoc = DocUpdater(doc).update(
            RequestBuilder(ByteArrayInputStream(json.trimIndent().toByteArray()))
                .buildRequest()
        )

        Assert.assertEquals("Alice", newDoc.getString("name"))
        Assert.assertEquals("F", newDoc.getString("gender"))
        Assert.assertEquals(20, newDoc.getInt("age"))

        val newAddr = newDoc.getDictionary("address")
        Assert.assertEquals("100 Wall Street", newAddr?.getString("streetAddress"))
        Assert.assertEquals("New York", newAddr?.getString("city"))
        Assert.assertEquals(10118L, newAddr?.getLong("zip"))

        val newChildren = newDoc.getArray("children")
        var newChild = newChildren?.getDictionary(0)
        Assert.assertEquals("Bob", newChild?.getString("name"))
        Assert.assertEquals("M", newChild?.getString("gender"))
        Assert.assertEquals(13.0F, newChild?.getFloat("age"))

        newChild = newChildren?.getDictionary(1)
        Assert.assertEquals("Carol", newChild?.getString("name"))
        Assert.assertEquals("F", newChild?.getString("gender"))
        Assert.assertEquals(16.5F, newChild?.getFloat("age"))
    }
}
