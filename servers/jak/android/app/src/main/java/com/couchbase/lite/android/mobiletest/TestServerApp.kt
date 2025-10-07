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

import android.app.Application
import android.os.StrictMode
import com.couchbase.lite.mobiletest.Server
import com.couchbase.lite.mobiletest.TestApp
import org.koin.android.ext.koin.androidContext
import org.koin.androidx.viewmodel.dsl.viewModel
import org.koin.core.context.GlobalContext
import org.koin.dsl.module

class TestServerApp : Application() {
    @Suppress("USELESS_CAST")
    override fun onCreate() {
        super.onCreate()

        StrictMode.setVmPolicy(
            StrictMode.VmPolicy.Builder().detectAll().penaltyLog().build()
        )
        StrictMode.setThreadPolicy(
            StrictMode.ThreadPolicy.Builder().detectAll().penaltyLog().build()
        )

        TestApp.init(AndroidTestApp(this))

        // Enable Koin dependency injection framework
        GlobalContext.startKoin {
            // inject Android context
            androidContext(this@TestServerApp)

            // dependency register modules
            modules(
                module {
                    // this cast *does* appear to be necessary
                    single { Server() as Server }

                    viewModel { MainViewModel(get()) }
                })
        }
    }
}
