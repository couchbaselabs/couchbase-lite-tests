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
package com.couchbase.lite.android.mobiletest

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.couchbase.lite.mobiletest.util.Log
import com.couchbase.lite.mobiletest.Server
import com.couchbase.lite.mobiletest.TestApp
import java.io.IOException


private const val TAG = "MAIN"

class MainActivity : AppCompatActivity() {
    private var server: Server? = null
    private var status: TextView? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        status = findViewById(R.id.status)
    }

    override fun onStart() {
        super.onStart()
        val id = TestApp.getApp().appId
        val server = Server(id)


        val port = server.myPort
        Log.i(TAG, "Server launched at $id:$port")
        status?.text = getString(R.string.running, id, port)
        try {
            server.start()
            this.server = server
        } catch (e: IOException) {
            Log.e(TAG, "Failed starting server", e)
            status?.text = getString(R.string.fail)
            finish()
        }
    }

    override fun onStop() {
        super.onStop()
        server?.stop()
        status?.setText(R.string.stopped)
    }
}
