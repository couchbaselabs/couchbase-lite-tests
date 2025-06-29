
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
package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;

import com.couchbase.lite.mobiletest.endpoints.v1.Session;


public final class TestContext extends BaseTestContext {
    public TestContext(@NonNull TestApp app, @NonNull Session session, @NonNull String testName) {
        super(app, session, testName);
    }

    @NonNull
    @Override
    protected TestContext getTestContext() { return this; }
}
