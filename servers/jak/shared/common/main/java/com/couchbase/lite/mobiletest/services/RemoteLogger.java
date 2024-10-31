//
// Copyright (c) 2024 Couchbase, Inc All rights reserved.
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

import androidx.annotation.GuardedBy;
import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

import com.couchbase.lite.LogDomain;
import com.couchbase.lite.LogLevel;
import com.couchbase.lite.mobiletest.errors.ServerError;


@SuppressWarnings({"PMD.UnusedPrivateField", "PMD.SingularField"})
public class RemoteLogger extends Log.TestLogger {
    private static final String TAG = "REMLOG";


    @NonNull
    private final String url;
    @NonNull
    private final String sessionId;
    @NonNull
    private final String tag;

    @Nullable
    @GuardedBy("url")
    private WebSocket webSocket;

    public RemoteLogger(@NonNull String url, @NonNull String sessionId, @NonNull String tag) {
        this.url = url;
        this.sessionId = sessionId;
        this.tag = tag;
    }

    public void connect() {
        new OkHttpClient.Builder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
            .newWebSocket(
                new Request.Builder()
                    .url("\"ws://" + url + "/openLogStream")
                    .header("CBL-Log-ID", sessionId)
                    .header("CBL-Log-Tag", tag)
                    .get()
                    .build(),
                new WebSocketListener() {
                    @Override
                    public void onOpen(@NonNull WebSocket socket, @NonNull Response resp) {
                        if (!resp.isSuccessful()) {
                            fail("Failed starting new log response: " + resp.code());
                        }
                        synchronized (url) { webSocket = socket; }
                    }

                    @Override
                    public void onMessage(@NonNull WebSocket webSocket, @NonNull String text) {
                        fail("Unexpected message from LogSlurper: " + text);
                    }

                    @Override
                    public void onFailure(@NonNull WebSocket webSocket, @NonNull Throwable t, @Nullable Response resp) {
                        fail("WebSocket error: " + t.getMessage(), t);
                        close();
                    }

                    @Override
                    public void onClosed(@NonNull WebSocket webSocket, int code, @NonNull String reason) { close(); }
                });
    }

    @Override
    public void log(@NonNull LogLevel level, @NonNull LogDomain domain, @NonNull String msg) {
        log(level, domain.toString(), msg, null);
    }

    @Override
    public void log(LogLevel level, String tag, String msg, Exception err) {
        final WebSocket socket;
        synchronized (url) { socket = webSocket; }

        if (socket == null) {
            Log.p(TAG, "RemoteLogger is not connected");
            return;
        }

        final StringBuilder logMsg = new StringBuilder();
        logMsg.append(tag).append('/').append(level.toString()).append(' ').append(msg);

        if (err != null) {
            final StringWriter sw = new StringWriter();
            err.printStackTrace(new PrintWriter(sw));
            logMsg.append(System.lineSeparator()).append(sw);
        }

        socket.send(logMsg.toString());
    }

    @Override
    public void close() {
        final WebSocket socket;
        synchronized (url) { socket = webSocket; }
        if (socket != null) { socket.close(1000, null); }
    }

    private void fail(String message) { fail(message, null); }

    private void fail(String message, Throwable e) {
        close();
        throw new ServerError(message, e);
    }
}
