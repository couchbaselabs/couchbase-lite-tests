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

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

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
    private static final long TIMEOUT_SECS = 30;

    @NonNull
    private final WebSocketListener listener = new WebSocketListener() {
        @Override
        public void onOpen(@NonNull WebSocket socket, @NonNull Response resp) {
            if (!(resp.isSuccessful() || (resp.code() == 101))) { fail("Failed starting new log: " + resp.code()); }
            final WebSocket oSocket = webSocket.getAndSet(socket);
            startLatch.countDown();
            if (oSocket != null) { fail("Unexpected WebSocket open"); }
        }

        @Override
        public void onMessage(@NonNull WebSocket webSocket, @NonNull String text) {
            Log.p(TAG, "Unexpected message from LogSlurper: " + text);
        }

        @Override
        public void onFailure(@NonNull WebSocket webSocket, @NonNull Throwable t, @Nullable Response resp) {
            stopLatch.countDown();
            startLatch.countDown();
            fail("WebSocket error", t);
        }

        @Override
        public void onClosed(@NonNull WebSocket webSocket, int code, @NonNull String reason) {
            stopLatch.countDown();
            startLatch.countDown();
            close(1000, "Closed");
        }
    };

    @NonNull
    private final CountDownLatch startLatch = new CountDownLatch(1);
    @NonNull
    private final CountDownLatch stopLatch = new CountDownLatch(1);
    @NonNull
    private final AtomicReference<WebSocket> webSocket = new AtomicReference<>();
    @NonNull
    private final AtomicBoolean connected = new AtomicBoolean();

    @NonNull
    private final String url;
    @NonNull
    private final String sessionId;
    @NonNull
    private final String tag;


    public RemoteLogger(@NonNull String url, @NonNull String sessionId, @NonNull String tag,
                        @NonNull LogLevel level, @NonNull LogDomain... domains) {
        super(level, domains); // Pass to BaseLogSink constructor for immutability [attached_file:1]
        this.url = url;
        this.sessionId = sessionId;
        this.tag = tag;
    }

    // Synchronously open a connection to the remote log server.
    public void connect() {
        if (connected.getAndSet(true)) { throw new ServerError("Attempt to reuse a RemoteLogger"); }

        new OkHttpClient.Builder()
            .readTimeout(0, TimeUnit.MILLISECONDS)
            .build()
            .newWebSocket(
                new Request.Builder()
                    .url("http://" + url + "/openLogStream")
                    .header("CBL-Log-ID", sessionId)
                    .header("CBL-Log-Tag", tag)
                    .get()
                    .build(),
                listener);

        try {
            if (startLatch.await(10, TimeUnit.SECONDS)) { return; }
        }
        catch (InterruptedException ignore) { }
        fail("Failed opening LogSlurper websocket");

    }

    @Override
    public void writeLog(LogLevel level, LogDomain domain, String message) {
        final WebSocket socket = webSocket.get();
        if (socket == null) {
            Log.p(TAG, "RemoteLogger is not connected");
            return;
        }

        sendLogMessage(socket, new StringBuilder(tag).append('/').append(level).append(' ').append(message).toString());
    }

    @Override
    public void close() { close(1001, "Closed by client"); }

    private void sendLogMessage(@NonNull WebSocket socket, @NonNull String message) {
        if (!socket.send(message)) { Log.p(TAG, "Failed to send log message"); }
    }

    private void fail(String message) { fail(message, null); }

    private void fail(String message, Throwable e) {
        close(1011, message);
        throw new ServerError(message, e);
    }

    // Synchronously close the connection to the remote log server.
    private void close(int code, @NonNull String reason) {
        final WebSocket socket = webSocket.getAndSet(null);
        if (socket == null) { return; }

        socket.close(code, reason);
        try {
            if (stopLatch.await(TIMEOUT_SECS, TimeUnit.SECONDS)) { return; }
        }
        catch (InterruptedException ignore) { }
        Log.p(TAG, "Failed closing LogSlurper websocket");
    }
}
