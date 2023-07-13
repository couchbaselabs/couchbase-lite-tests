package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;

import java.io.OutputStream;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.nanohttpd.protocols.http.IHTTPSession;
import org.nanohttpd.protocols.http.NanoHTTPD;
import org.nanohttpd.protocols.http.request.Method;
import org.nanohttpd.protocols.http.response.IStatus;
import org.nanohttpd.protocols.http.response.Response;
import org.nanohttpd.protocols.http.response.Status;

import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class Server extends NanoHTTPD {
    private static final String TAG = "SERVER";

    private static final int PORT = 8080;

    private static class SafeResponse extends Response {
        private static final Map<Reply.Status, IStatus> STATUS;
        static {
            final Map<Reply.Status, IStatus> m = new HashMap<>();
            m.put(Reply.Status.OK, Status.OK);
            m.put(Reply.Status.BAD_REQUEST, Status.BAD_REQUEST);
            m.put(Reply.Status.METHOD_NOT_ALLOWED, Status.METHOD_NOT_ALLOWED);
            STATUS = Collections.unmodifiableMap(m);
        }

        private final Reply reply;

        SafeResponse(@NonNull Reply reply) {
            super(
                STATUS.get(reply.getStatus()),
                reply.getContentType(),
                reply.getContent(),
                reply.getSize());
            this.reply = reply;
        }

        @Override
        public void send(OutputStream outputStream) {
            try { super.send(outputStream); }
            finally { reply.close(); }
        }
    }

    private static final Map<Method, Dispatcher.Method> METHODS;
    static {
        final Map<Method, Dispatcher.Method> m = new HashMap<>();
        m.put(Method.GET, Dispatcher.Method.GET);
        m.put(Method.PUT, Dispatcher.Method.PUT);
        m.put(Method.POST, Dispatcher.Method.POST);
        m.put(Method.DELETE, Dispatcher.Method.DELETE);
        METHODS = Collections.unmodifiableMap(m);
    }


    private final String appId;
    private final Dispatcher dispatcher;

    public Server() {
        super(PORT);
        final TestApp app = TestApp.getApp();
        appId = app.getAppId();
        dispatcher = app.getDispatcher();
    }

    @SuppressWarnings("PMD.PreserveStackTrace")
    @NonNull
    @Override
    public Response handle(@NonNull IHTTPSession session) {
        int version = TestApp.DEFAULT_PROTOCOL_VERSION;
        Response resp;
        Reply reply = null;
        try {
            final Map<String, String> headers = session.getHeaders();

            final String versionStr = headers.get(TestApp.HEADER_PROTOCOL_VERSION);
            if (versionStr == null) {
                Log.w(TAG, "Request does not specify a protocol version. Using version " + version);
            }
            else {
                try { version = Integer.parseInt(versionStr); }
                catch (NumberFormatException ignore) {
                    Log.w(TAG, "Unrecognized protocol version: " + versionStr + ". Using version " + version);
                }
            }

            String client = headers.get(TestApp.HEADER_SENDER);
            if (client == null) {
                client = TestApp.DEFAULT_CLIENT;
                Log.w(TAG, "Request does not specify a client Id. Using " + client);
            }

            final Dispatcher.Method method = METHODS.get(session.getMethod());
            if (method == null) { throw new IllegalArgumentException("Unimplemented method: " + session.getMethod()); }

            final String endpoint = session.getUri();
            if (StringUtils.isEmpty(endpoint)) { throw new IllegalArgumentException("Empty request"); }

            Log.i(TAG, "Request(" + version + ")@" + client + " " + method + ":" + endpoint);

            reply = dispatcher.handleRequest(client, version, method, endpoint, session.getInputStream());
            resp = new SafeResponse(reply);
        }
        catch (Exception err) {
            Log.w(TAG, "Server error", err);
            if (reply != null) { reply.close(); }
            resp = Response.newFixedLengthResponse(
                Status.INTERNAL_ERROR,
                "text/plain",
                TestException.printError(err));
        }

        resp.addHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
        resp.addHeader(TestApp.HEADER_SENDER, appId);

        return resp;
    }
}
