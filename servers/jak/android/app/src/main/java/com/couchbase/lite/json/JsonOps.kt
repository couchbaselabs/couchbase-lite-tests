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
package com.couchbase.lite.json

import android.util.Log
import org.json.JSONArray
import org.json.JSONObject

fun JSONObject.jPrint() = JsonEach().forEach(this, JsonPrinter(""))

fun JSONArray.jPrint() = JsonEach().forEach(this, JsonPrinter(""))

fun JSONObject.jUpdateFrom(src: JSONObject) = JsonEach().forEach(src, JsonObjUpdate(this))

fun JSONArray.jUpdateFrom(src: JSONArray) = JsonEach().forEach(src, JsonArrayUpdate(this))

fun JSONObject.jIsIdenticalTo(target: JSONObject) = JsonReduce<Boolean>().reduce(this, JsonObjCompare(target), true)

fun JSONArray.jIsIdenticalTo(target: JSONArray) = JsonReduce<Boolean>().reduce(this, JsonArrayCompare(target), true)


class JsonEach {
    interface ObjectOp {
        fun startObject(key: String): ObjectOp?
        fun startArray(key: String): ArrayOp?
        fun strVal(key: String, str: String)
        fun numVal(key: String, num: Number)
        fun boolVal(key: String, bool: Boolean)
        fun nullVal(key: String)
        fun endObject()
    }

    interface ArrayOp {
        fun startObject(idx: Int): ObjectOp?
        fun startArray(idx: Int): ArrayOp?
        fun strVal(idx: Int, str: String)
        fun numVal(idx: Int, num: Number)
        fun boolVal(idx: Int, bool: Boolean)
        fun nullVal(idx: Int)
        fun endArray()
    }

    fun forEach(obj: JSONObject, block: ObjectOp) {
        val keys = obj.keys()
        for (key in keys) {
            when (val value = obj.get(key)) {
                is JSONObject -> block.startObject(key)?.let { forEach(value, it) }
                is JSONArray -> block.startArray(key)?.let { forEach(value, it) }
                is String -> block.strVal(key, value)
                is Number -> block.numVal(key, value)
                is Boolean -> block.boolVal(key, value)
                JSONObject.NULL -> block.nullVal(key)
                else -> throw IllegalArgumentException("unrecognized JSON type: ${value::class.java.name}")
            }
        }
        block.endObject()
    }

    fun forEach(array: JSONArray, block: ArrayOp) {
        val n = array.length()
        for (idx in 0 until n) {
            when (val elem = array.get(idx)) {
                is JSONObject -> block.startObject(idx)?.let { forEach(elem, it) }
                is JSONArray -> block.startArray(idx)?.let { forEach(elem, it) }
                is String -> block.strVal(idx, elem)
                is Number -> block.numVal(idx, elem)
                is Boolean -> block.boolVal(idx, elem)
                JSONObject.NULL -> block.nullVal(idx)
                else -> throw IllegalArgumentException("unrecognized JSON type: ${elem::class.java.name}")
            }
        }
        block.endArray()
    }
}

class JsonReduce<T> {
    interface ObjectOp<T> {
        fun startObject(key: String, acc: T): ObjectOp<T>?
        fun startArray(key: String, acc: T): ArrayOp<T>?
        fun strVal(key: String, str: String, acc: T): T
        fun numVal(key: String, num: Number, acc: T): T
        fun boolVal(key: String, bool: Boolean, acc: T): T
        fun nullVal(key: String, acc: T): T
        fun endObject(acc: T): T
    }

    interface ArrayOp<T> {
        fun startObject(idx: Int, acc: T): ObjectOp<T>?
        fun startArray(idx: Int, acc: T): ArrayOp<T>?
        fun strVal(idx: Int, str: String, acc: T): T
        fun numVal(idx: Int, num: Number, acc: T): T
        fun boolVal(idx: Int, bool: Boolean, acc: T): T
        fun nullVal(idx: Int, acc: T): T
        fun endArray(acc: T): T
    }

    fun reduce(obj: JSONObject, visitor: ObjectOp<T>, acc: T): T {
        val keys = obj.keys()
        var ret = acc
        for (key in keys) {
            when (val value = obj.get(key)) {
                is JSONObject -> visitor.startObject(key, ret)?.let { ret = reduce(value, it, ret) }
                is JSONArray -> visitor.startArray(key, ret)?.let { ret = reduce(value, it, ret) }
                is String -> ret = visitor.strVal(key, value, ret)
                is Number -> ret = visitor.numVal(key, value, ret)
                is Boolean -> ret = visitor.boolVal(key, value, ret)
                JSONObject.NULL -> ret = visitor.nullVal(key, ret)
                else -> throw IllegalArgumentException("unrecognized JSON type: ${value::class.java.name}")
            }
        }
        return visitor.endObject(ret)
    }

    fun reduce(array: JSONArray, visitor: ArrayOp<T>, acc: T): T {
        val n = array.length()
        var ret = acc
        for (idx in 0 until n) {
            when (val elem = array.get(idx)) {
                is JSONObject -> visitor.startObject(idx, ret)?.let {
                    ret = reduce(elem, it, ret)
                }
                is JSONArray -> visitor.startArray(idx, ret)?.let {
                    ret = reduce(elem, it, ret)
                }
                is String -> ret = visitor.strVal(idx, elem, ret)
                is Number -> ret = visitor.numVal(idx, elem, ret)
                is Boolean -> ret = visitor.boolVal(idx, elem, ret)
                JSONObject.NULL -> ret = visitor.nullVal(idx, ret)
                else -> throw IllegalArgumentException("unrecognized JSON type: ${elem::class.java.name}")
            }
        }
        return visitor.endArray(ret)
    }
}

private class JsonPrinter(private val tag: String) : JsonEach.ObjectOp, JsonEach.ArrayOp {
    companion object {
        const val TAG = "JPRINT"
    }

    override fun startObject(key: String): JsonEach.ObjectOp {
        Log.d(TAG, "start object @${key}")
        return JsonPrinter(key)
    }

    override fun startObject(idx: Int): JsonEach.ObjectOp {
        Log.d(TAG, "start object @${idx}")
        return JsonPrinter(idx.toString())
    }

    override fun endObject() {
        Log.d(TAG, "end object @${tag}")
    }

    override fun startArray(key: String): JsonEach.ArrayOp {
        Log.d(TAG, "start array @${key}")
        return JsonPrinter(key)
    }

    override fun startArray(idx: Int): JsonEach.ArrayOp {
        Log.d(TAG, "start array @${idx}")
        return JsonPrinter(idx.toString())
    }

    override fun endArray() {
        Log.d(TAG, "end array @${tag}")
    }

    override fun strVal(key: String, str: String) {
        Log.d(TAG, "string @${key}: ${str}")
    }

    override fun strVal(idx: Int, str: String) {
        Log.d(TAG, "string @${idx}: ${str}")
    }

    override fun numVal(key: String, num: Number) {
        Log.d(TAG, "number @${key}: ${num}")
    }

    override fun numVal(idx: Int, num: Number) {
        Log.d(TAG, "number @${idx}: ${num}")
    }

    override fun boolVal(key: String, bool: Boolean) {
        Log.d(TAG, "bool @${key}: ${bool}")
    }

    override fun boolVal(idx: Int, bool: Boolean) {
        Log.d(TAG, "bool @${idx}: ${bool}")
    }

    override fun nullVal(key: String) {
        Log.d(TAG, "null @${key}")
    }

    override fun nullVal(idx: Int) {
        Log.d(TAG, "null @${idx}")
    }
}

private class JsonObjCompare(private val target: JSONObject) : JsonReduce.ObjectOp<Boolean> {
    private var keys = target.keys().asSequence().toMutableList()

    override fun startObject(key: String, acc: Boolean): JsonReduce.ObjectOp<Boolean>? {
        keys.remove(key)
        val obj = target.optJSONObject(key)
        return if (!acc || (obj == null)) null else JsonObjCompare(obj)
    }

    override fun startArray(key: String, acc: Boolean): JsonReduce.ArrayOp<Boolean>? {
        keys.remove(key)
        val array = target.optJSONArray(key)
        return if (!acc || (array == null)) null else JsonArrayCompare(array)
    }

    override fun strVal(key: String, str: String, acc: Boolean): Boolean {
        keys.remove(key)
        if (!acc) return false
        return str == target.optString(key)
    }

    override fun numVal(key: String, num: Number, acc: Boolean): Boolean {
        keys.remove(key)
        if (!acc) return false
        return when (num) {
            is Int -> num == target.optInt(key)
            is Long -> num == target.optLong(key)
            is Double -> num == target.optDouble(key)
            else -> throw IllegalArgumentException("unrecognized Number: ${num::class.java.name}")
        }
    }

    override fun boolVal(key: String, bool: Boolean, acc: Boolean): Boolean {
        keys.remove(key)
        if (!acc) return false
        return bool == target.optBoolean(key)
    }

    override fun nullVal(key: String, acc: Boolean): Boolean {
        keys.remove(key)
        if (!acc) return false
        return target.isNull(key)
    }

    override fun endObject(acc: Boolean) = acc && keys.isEmpty()
}

private class JsonArrayCompare(private val target: JSONArray) : JsonReduce.ArrayOp<Boolean> {
    private val indices = Array(target.length()) { false }

    override fun startObject(idx: Int, acc: Boolean): JsonReduce.ObjectOp<Boolean>? {
        indices[idx] = true
        val obj = target.optJSONObject(idx)
        return if (!acc || (obj == null)) null else JsonObjCompare(obj)
    }

    override fun startArray(idx: Int, acc: Boolean): JsonReduce.ArrayOp<Boolean>? {
        indices[idx] = true
        val array = target.optJSONArray(idx)
        return if (!acc || (array == null)) null else JsonArrayCompare(array)
    }

    override fun strVal(idx: Int, str: String, acc: Boolean): Boolean {
        indices[idx] = true
        return str == target.optString(idx)
    }

    override fun numVal(idx: Int, num: Number, acc: Boolean): Boolean {
        indices[idx] = true
        return when (num) {
            is Int -> num == target.optInt(idx)
            is Long -> num == target.optLong(idx)
            is Double -> num == target.optDouble(idx)
            else -> throw IllegalArgumentException("unrecognized Number: ${num::class.java.name}")
        }
    }

    override fun boolVal(idx: Int, bool: Boolean, acc: Boolean): Boolean {
        indices[idx] = true
        return bool == target.optBoolean(idx)
    }

    override fun nullVal(idx: Int, acc: Boolean): Boolean {
        indices[idx] = true
        return target.isNull(idx)
    }

    override fun endArray(acc: Boolean) = acc && (null == indices.firstOrNull { !it })
}

private class JsonObjUpdate(private val target: JSONObject) : JsonEach.ObjectOp {
    override fun startObject(key: String): JsonEach.ObjectOp {
        return JsonObjUpdate(target.optJSONObject(key) ?: JSONObject().also { target.put(key, it) })
    }

    override fun startArray(key: String): JsonEach.ArrayOp {
        return JsonArrayUpdate(target.optJSONArray(key) ?: JSONArray().also { target.put(key, it) })
    }

    override fun strVal(key: String, str: String) {
        if (str != target.optString(key)) target.put(key, str)
    }

    override fun numVal(key: String, num: Number) {
        val needsUpdate = when (num) {
            is Int -> num != target.optInt(key)
            is Long -> num != target.optLong(key)
            is Double -> num != target.optDouble(key)
            else -> throw IllegalArgumentException("unrecognized Number: ${num::class.java.name}")
        }
        if (needsUpdate) target.put(key, num)
    }

    override fun boolVal(key: String, bool: Boolean) {
        if (bool != target.optBoolean(key)) target.put(key, bool)
    }

    override fun nullVal(key: String) {
        if (!target.isNull(key)) target.put(key, JSONObject.NULL)
    }

    override fun endObject() = Unit
}

private class JsonArrayUpdate(private val target: JSONArray) : JsonEach.ArrayOp {
    override fun startObject(idx: Int): JsonEach.ObjectOp {
        return JsonObjUpdate(target.optJSONObject(idx) ?: JSONObject().also { target.put(idx, it) })
    }

    override fun startArray(idx: Int): JsonEach.ArrayOp {
        return JsonArrayUpdate(target.optJSONArray(idx) ?: JSONArray().also { target.put(idx, it) })
    }

    override fun strVal(idx: Int, str: String) {
        if (str != target.getString(idx)) target.put(idx, str)
    }

    override fun numVal(idx: Int, num: Number) {
        val needsUpdate = when (num) {
            is Int -> num != target.getInt(idx)
            is Long -> num != target.getLong(idx)
            is Double -> num != target.getDouble(idx)
            else -> throw IllegalArgumentException("unrecognized Number: ${num::class.java.name}")
        }
        if (needsUpdate) target.put(idx, num)
    }

    override fun boolVal(idx: Int, bool: Boolean) {
        if (bool != target.getBoolean(idx)) target.put(idx, bool)
    }

    override fun nullVal(idx: Int) {
        if (!target.isNull(idx)) target.put(idx, JSONObject.NULL)
    }

    override fun endArray() = Unit
}
