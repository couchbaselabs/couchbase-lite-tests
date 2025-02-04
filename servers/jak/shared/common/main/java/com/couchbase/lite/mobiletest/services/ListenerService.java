//
// Copyright (c) 2025 Couchbase, Inc All rights reserved.
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

package com.couchbase.lite.mobiletest.services;

import androidx.annotation.NonNull;

import java.util.UUID;

import com.couchbase.lite.URLEndpointListener;
import com.couchbase.lite.mobiletest.TestContext;
import com.couchbase.lite.mobiletest.errors.ClientError;


public class ListenerService {
    public void init(@NonNull TestContext ignore1) {
        // nothing to do here...
    }

    @NonNull
    public String addListener(@NonNull TestContext ctxt, @NonNull URLEndpointListener listener) {
        final String listenerId = UUID.randomUUID().toString();
        ctxt.addEndptListener(listenerId, listener);
        return listenerId;
    }

    public void stopListener(@NonNull TestContext ctxt, @NonNull String listenerId) {
        final URLEndpointListener listener = ctxt.getEndptListener(listenerId);
        if (listener == null) { throw new ClientError("No such listener: " + listenerId); }
        listener.stop();
    }
}
