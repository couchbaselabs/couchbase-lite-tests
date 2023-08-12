package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
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
import com.couchbase.lite.mobiletest.tools.ErrorBuilder;
import com.couchbase.lite.mobiletest.tools.ReplyBuilder;
import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class Server extends NanoHTTPD {
    private static final String TAG = "SERVER";

    private static final int PORT = 8080;

    private static class SafeResponse extends Response {
        private final Reply reply;

        SafeResponse(@NonNull Status status, @NonNull Reply reply) {
            super(status, "application/json", reply.getContent(), reply.getSize());
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

    @SuppressWarnings({"PMD.PreserveStackTrace", "PMD.CloseResource"})
    @SuppressFBWarnings("REC_CATCH_EXCEPTION")
    @NonNull
    @Override
    public Response handle(@NonNull IHTTPSession session) {
        int version = -1;
        Response resp;
        Reply reply = null;
        try {
            final Map<String, String> headers = session.getHeaders();

            final String versionStr = headers.get(TestApp.HEADER_PROTOCOL_VERSION);
            if (versionStr != null) {
                try {
                    final int v = Integer.parseInt(versionStr);
                    if (TestApp.KNOWN_VERSIONS.contains(v)) { version = v; }
                }
                catch (NumberFormatException ignore) { }
            }

            final Dispatcher.Method method = METHODS.get(session.getMethod());
            if (method == null) { throw new ClientError("Unimplemented method: " + session.getMethod()); }

            final String endpoint = session.getUri();
            if (StringUtils.isEmpty(endpoint)) { throw new ClientError("Empty request"); }

            String client = headers.get(TestApp.HEADER_CLIENT);

            Log.i(TAG, "Request " + client + "(" + version + "): " + method + " " + endpoint);

            InputStream req = session.getInputStream();

            // Special handling for the 'GET /' endpoint
            if ("/".equals(endpoint) && (Dispatcher.Method.GET.equals(method))) {
                if (version < 0) { version = TestApp.LATEST_SUPPORTED_PROTOCOL_VERSION; }
                if (client == null) { client = "anonymous"; }
                // This is particularly annoying.
                // GET really shouldn't have a req.... but we did agree at one time
                // that all interactions between the client and the server would contain an object.
                // !!! This needs a better solution.  GETs don't have requests.
                req = new ByteArrayInputStream("{}".getBytes(StandardCharsets.UTF_8));
            }
            if (version < 0) { throw new ClientError("No protocol version specified"); }
            if (client == null) { throw new ClientError("No client specified"); }

            reply = dispatcher.handleRequest(client, version, method, endpoint, req);
            resp = new SafeResponse(Status.OK, reply);
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
        try {
            return new SafeResponse(status, new Reply(new ReplyBuilder(new ErrorBuilder(err).build()).buildReply()));
        }
        catch (Exception e) {
            Log.w(TAG, "Catastrophic server failure", e);
            return Response.newFixedLengthResponse(Status.INTERNAL_ERROR, "text/plain", err.toString());
        }
    }
}
