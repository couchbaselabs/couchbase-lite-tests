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

import com.couchbase.lite.mobiletest.util.Json
import org.junit.Assert
import org.junit.Test
import java.io.ByteArrayInputStream

class JsonTest : BaseTest() {
    @Test
    fun testArgs() {
        val stream = ByteArrayInputStream("{\"this\": { \"foo\": \"L55\"}}".toByteArray(Charsets.UTF_8))

        val parsed = Json().parse(stream, Map::class.java)

        Assert.assertEquals(55L, (parsed["this"] as Map<*, *>?)?.get("foo"))
    }
}