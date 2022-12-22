//
// Copyright (c) 2019 Couchbase, Inc All rights reserved.
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
package com.couchbase.lite.android.mobiletest;

import java.nio.charset.StandardCharsets;

import org.junit.Assert;
import org.junit.Test;

import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.Reply;
import com.couchbase.lite.mobiletest.TestApp;


public class SimpleTest {

    @Test
    public void testGetVersion() throws Exception {
        final Reply r = TestApp.getApp().getDispatcher().run("version", null, Memory.create("test"));
        Assert.assertNotNull(r);
        Assert.assertEquals("text/plain", r.getContentType());
        Assert.assertEquals("\"Test Server (", new String(r.getData(), StandardCharsets.UTF_8).substring(0, 14));
    }
}
