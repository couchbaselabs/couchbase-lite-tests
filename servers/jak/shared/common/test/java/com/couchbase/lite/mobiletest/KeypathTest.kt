//
// Copyright (c) 2023 Couchbase, Inc All rights reserved.
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

import com.couchbase.lite.Document
import com.couchbase.lite.MutableArray
import com.couchbase.lite.MutableDictionary
import com.couchbase.lite.MutableDocument
import com.couchbase.lite.mobiletest.changes.KeypathParser
import com.couchbase.lite.mobiletest.errors.ClientError
import org.junit.Assert
import org.junit.Test


class KeypathTest {

    @Test
    fun testGoodPath01() {
        KeypathParser().parse("$.test")
    }

    @Test
    fun testGoodPath02() {
        KeypathParser().parse("\\$.test")
    }

    @Test
    fun testGoodPath03() {
        KeypathParser().parse("test2.nested")
    }

    @Test
    fun testGoodPath04() {
        KeypathParser().parse("test2.\\[")
    }

    @Test
    fun testGoodPath05() {
        KeypathParser().parse("test2.\\]")
    }

    @Test
    fun testGoodPath06() {
        KeypathParser().parse("test2.\\.")
    }

    @Test
    fun testGoodPath07() {
        KeypathParser().parse("test2.foo\\]")
    }

    @Test
    fun testGoodPath08() {
        KeypathParser().parse("test2.foo\\[bar")
    }

    @Test
    fun testGoodPath09() {
        KeypathParser().parse("test2.foo\\]bar")
    }

    @Test
    fun testGoodPath10() {
        KeypathParser().parse("test2.foo\\.bar")
    }

    @Test
    fun testGoodPath11() {
        KeypathParser().parse("test3[3]")
    }

    @Test
    fun testGoodPath12() {
        KeypathParser().parse("test4.$")
    }

    @Test
    fun testGoodPath13() {
        KeypathParser().parse("name.secret")
    }

    @Test
    fun testGoodPath14() {
        KeypathParser().parse("name.other_secret.super_secret")
    }

    @Test
    fun testGoodPath15() {
        KeypathParser().parse("contact")
    }

    @Test
    fun testGoodPath16() {
        KeypathParser().parse("likes")
    }

    @Test(expected = ClientError::class)
    fun testBadPath01() {
        KeypathParser().parse("")
    }

    @Test(expected = ClientError::class)
    fun testBadPath02() {
        KeypathParser().parse(".")
    }

    @Test(expected = ClientError::class)
    fun testBadPath03() {
        KeypathParser().parse("[")
    }

    @Test(expected = ClientError::class)
    fun testBadPath04() {
        KeypathParser().parse("]")
    }

    @Test(expected = ClientError::class)
    fun testBadPath05() {
        KeypathParser().parse("\$")
    }

    @Test(expected = ClientError::class)
    fun testBadPath07() {
        KeypathParser().parse("$.")
    }

    @Test(expected = ClientError::class)
    fun testBadPath06() {
        KeypathParser().parse("\$x")
    }

    @Test(expected = ClientError::class)
    fun testBadPath08() {
        KeypathParser().parse("[12].")
    }

    @Test(expected = ClientError::class)
    fun testBadPath09() {
        KeypathParser().parse("foo.")
    }

    @Test(expected = ClientError::class)
    fun testBadPath10() {
        KeypathParser().parse("[123a]")
    }

    @Test(expected = ClientError::class)
    fun testBadPath11() {
        KeypathParser().parse("[12")
    }

    @Test(expected = ClientError::class)
    fun testBadPath12() {
        KeypathParser().parse("test[[")
    }

    @Test(expected = ClientError::class)
    fun testBadPath13() {
        KeypathParser().parse("test[]")
    }

    @Test(expected = ClientError::class)
    fun testBadPath14() {
        KeypathParser().parse("test.[3]")
    }

    @Test(expected = ClientError::class)
    fun testBadPath15() {
        KeypathParser().parse("test[3]]")
    }

    @Test(expected = ClientError::class)
    fun testBadPath16() {
        KeypathParser().parse("contact.email[-1]")
    }

    @Test
    fun testGetSimplePath() {
        val path = KeypathParser().parse("name")
        Assert.assertEquals("Eve", path.get(makeDoc().toMap()))
    }

    @Test
    fun testGetArrayPath() {
        val path = KeypathParser().parse("children[1].name")
        Assert.assertEquals("Carol", path.get(makeDoc().toMap()))
    }

    @Test
    fun testSetSimplePath() {
        val data = makeDoc().toMap()
        val path = KeypathParser().parse("address.city")
        path.set(data, "Dayton")

        Assert.assertEquals("Dayton", ((data["address"] as? Map<*, *>)?.get("city") as? String))
    }

    @Test
    fun testSetArrayPath() {
        val dave = HashMap<String, Any>()
        dave["name"] = "Dave"
        dave["gender"] = "M"
        dave["age"] = 10

        val data = makeDoc().toMap()
        val path = KeypathParser().parse("children[4]")
        path.set(data, dave)

        Assert.assertNull((data["children"] as? List<*>)?.get(3))
        Assert.assertEquals("Dave", (((data["children"] as? List<*>)?.get(4) as? Map<*, *>)?.get("name")))
    }

    private fun makeDoc(): Document {
        val address = MutableDictionary()
        address.setString("streetAddress", "140 E. Seventh St.")
        address.setString("city", "New York")

        val children = MutableArray()

        var child = MutableDictionary()
        child.setString("name", "Bob")
        child.setString("gender", "M")
        child.setInt("age", 12)
        children.addDictionary(child)

        child = MutableDictionary()
        child.setString("name", "Carol")
        child.setString("gender", "F")
        child.setInt("age", 18)
        children.addDictionary(child)

        val doc = MutableDocument()
        doc.setString("name", "Eve")
        doc.setString("gender", "F")
        doc.setArray("children", children)
        doc.setDictionary("address", address)

        return doc
    }

}