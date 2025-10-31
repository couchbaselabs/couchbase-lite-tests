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
import androidx.appcompat.app.AppCompatActivity
import com.couchbase.lite.android.mobiletest.databinding.ActivityMainBinding
import org.koin.androidx.viewmodel.ext.android.viewModel


class MainActivity : AppCompatActivity() {
    private lateinit var viewBinding: ActivityMainBinding
    private val model by viewModel<MainViewModel>()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        viewBinding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(viewBinding.root)
    }

    override fun onStart() {
        super.onStart()

        viewBinding.server.text = BuildConfig.SERVER_VERSION
        try {
            val uri = model.startServer()
            viewBinding.status.text = getString(R.string.running, uri?.toString() ?: "unknown")
        } catch (e: Exception) {
            viewBinding.status.text = getString(R.string.fail)
            finish()
        }
    }

    override fun onStop() {
        super.onStop()
        model.stopServer()
        viewBinding.status.setText(R.string.stopped)
    }
}
