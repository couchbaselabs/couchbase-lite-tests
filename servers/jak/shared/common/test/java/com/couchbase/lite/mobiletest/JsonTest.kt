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

import com.couchbase.lite.mobiletest.json.JsonV1
import com.couchbase.lite.mobiletest.json.JsonV2
import org.junit.Assert
import org.junit.Test
import java.io.ByteArrayInputStream

class JsonTest : BaseTest() {
    @Test
    fun testJson1Args() {
        val data: MutableMap<String, Any?> = mutableMapOf("red" to null)
        data["green"] = listOf(true, "string", 43, 44L, 2.71828F, 2.71828, Memory.Ref("x1"))

        val json = JsonV1().serializeReply(data)
        val parsed = JsonV1().parseTask(json.inputStream())

        Assert.assertNull(parsed["red"])

        val list = parsed["green"] as List<Any?>
        Assert.assertTrue(list[0] as Boolean)
        Assert.assertEquals("string", list[1])
        Assert.assertEquals(43, list[2])
        Assert.assertEquals(44L, list[3])
        Assert.assertEquals(2.71828F, list[4])
        Assert.assertEquals(2.71828, list[5])
        Assert.assertEquals("x1", (list[6] as Memory.Ref).key)
    }

    @Test
    fun testJson2Args() {
        val data: MutableMap<String, Any?> = mutableMapOf("red" to null)
        data["green"] = listOf(true, "string", 43, 44L, 2.71828F, 2.71828, Memory.Ref("x1"))

        val json = JsonV2().serializeReply(data)
        val parsed = JsonV2().parseTask(json.inputStream())

        Assert.assertNull(parsed["red"])

        val list = parsed["green"] as List<Any?>
        Assert.assertTrue(list[0] as Boolean)
        Assert.assertEquals("string", list[1])
        Assert.assertEquals(43L, list[2])
        Assert.assertEquals(44L, list[3])
        Assert.assertEquals(2.71828, list[4])
        Assert.assertEquals(2.71828, list[5])
        Assert.assertEquals("x1", (list[6] as Memory.Ref).key)
    }
}