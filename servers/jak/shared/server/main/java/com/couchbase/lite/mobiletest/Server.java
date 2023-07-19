package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.OutputStream;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;
import org.nanohttpd.protocols.http.IHTTPSession;
import org.nanohttpd.protocols.http.NanoHTTPD;
import org.nanohttpd.protocols.http.request.Method;
import org.nanohttpd.protocols.http.response.Response;
import org.nanohttpd.protocols.http.response.Status;

import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.errors.TestError;
import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class Server extends NanoHTTPD {
    private static final String TAG = "SERVER";

    private static final int PORT = 8080;

    private static class SafeResponse extends Response {
        private final Reply reply;

        SafeResponse(@NonNull Reply reply) {
            super(Status.OK, "application/json", reply.getContent(), reply.getSize());
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
    @SuppressFBWarnings("REC_CATCH_EXCEPTION")
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
                try {
                    final int v = Integer.parseInt(versionStr);
                    if (TestApp.KNOWN_VERSIONS.contains(v)) { version = v; }
                    else {
                        Log.w(TAG, "Unrecognized protocol version: " + versionStr + ". Using version " + version);
                    }
                }
                catch (NumberFormatException ignore) {
                    Log.w(TAG, "Unrecognized protocol version: " + versionStr + ". Using version " + version);
                }
            }

            String client = headers.get(TestApp.HEADER_CLIENT);
            if (client == null) {
                client = TestApp.DEFAULT_CLIENT;
                Log.w(TAG, "Request does not specify a client Id. Using " + client);
            }

            final Dispatcher.Method method = METHODS.get(session.getMethod());
            if (method == null) { throw new IllegalArgumentException("Unimplemented method: " + session.getMethod()); }

            final String endpoint = session.getUri();
            if (StringUtils.isEmpty(endpoint)) { throw new IllegalArgumentException("Empty request"); }

            Log.i(TAG, "Request " + client + "(" + version + "): " + method + " " + endpoint);

            reply = dispatcher.handleRequest(client, version, method, endpoint, session.getInputStream());
            resp = new SafeResponse(reply);
        }
        catch (ClientError err) {
            Log.w(TAG, "Client error", err);
            resp = handleError(reply, Status.BAD_REQUEST, err);
        }
        catch (ServerError err) {
            Log.w(TAG, "Server error", err);
            resp = handleError(reply, Status.INTERNAL_ERROR, err);
        }
        catch (Exception err) {
            Log.w(TAG, "Internal Server error", err);
            resp = handleError(reply, Status.INTERNAL_ERROR, new ServerError("Internal server error", err));
        }

        resp.addHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
        resp.addHeader(TestApp.HEADER_SERVER, appId);

        return resp;
    }

    @NonNull
    private Response handleError(@Nullable Reply reply, @NonNull Status status, @NonNull TestError err) {
        if (reply != null) { reply.close(); }
        return Response.newFixedLengthResponse(status, "text/plain", err.printError());
    }
}
