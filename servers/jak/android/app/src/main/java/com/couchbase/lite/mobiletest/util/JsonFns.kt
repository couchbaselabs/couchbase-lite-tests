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
package com.couchbase.lite.mobiletest.util

import com.couchbase.lite.mobiletest.json.CompareJsonArray
import com.couchbase.lite.mobiletest.json.UpdateJsonArray
import com.couchbase.lite.mobiletest.json.JsonEach
import com.couchbase.lite.mobiletest.json.CompareJsonObject
import com.couchbase.lite.mobiletest.json.UpdateJsonObject
import com.couchbase.lite.mobiletest.json.PrintJson
import com.couchbase.lite.mobiletest.json.JsonReduce
import org.json.JSONArray
import org.json.JSONObject


fun JSONObject.jPrint() = JsonEach().forEach(this, PrintJson(""))

fun JSONArray.jPrint() = JsonEach().forEach(this, PrintJson(""))

fun JSONObject.jUpdateFrom(src: JSONObject) = JsonEach().forEach(src,
    UpdateJsonObject(this)
)

fun JSONArray.jUpdateFrom(src: JSONArray) = JsonEach().forEach(src,
    UpdateJsonArray(this)
)

fun JSONObject.jIsIdenticalTo(target: JSONObject): Boolean =
    JsonReduce<Boolean>().reduce(this,
        CompareJsonObject(target), true)

fun JSONArray.jIsIdenticalTo(target: JSONArray): Boolean =
    JsonReduce<Boolean>().reduce(this,
        CompareJsonArray(target), true)
