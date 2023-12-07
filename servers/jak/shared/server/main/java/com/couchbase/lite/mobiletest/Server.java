package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.OutputStream;
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
import com.couchbase.lite.mobiletest.json.ErrorBuilder;
import com.couchbase.lite.mobiletest.json.ReplyBuilder;
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


    private final String appId;
    private final GetDispatcher getDispatcher;
    private final PostDispatcher postDispatcher;

    public Server() {
        super(PORT);
        final TestApp app = TestApp.getApp();
        appId = app.getAppId();
        getDispatcher = new GetDispatcher(app);
        postDispatcher = new PostDispatcher(app);
    }

    @SuppressWarnings({"PMD.PreserveStackTrace", "PMD.CloseResource"})
    @SuppressFBWarnings("NP_LOAD_OF_KNOWN_NULL_VALUE")
    @NonNull
    @Override
    public Response handle(@NonNull IHTTPSession session) {
        int version = -1;
        Response resp;
        Reply reply = null;
        try {
            final Method method = session.getMethod();
            if (method == null) { throw new ServerError("Null HTTP method"); }

            final Map<String, String> headers = session.getHeaders();

            final String versionStr = headers.get(TestApp.HEADER_PROTOCOL_VERSION);
            if (versionStr != null) {
                try {
                    final int v = Integer.parseInt(versionStr);
                    if (TestApp.KNOWN_VERSIONS.contains(v)) { version = v; }
                }
                catch (NumberFormatException ignore) { }
            }

            final String endpoint = session.getUri();
            if (StringUtils.isEmpty(endpoint)) { throw new ClientError("Empty request"); }

            final String client = headers.get(TestApp.HEADER_CLIENT);
            final String contentType = headers.get(TestApp.HEADER_CONTENT_TYPE);

            Log.p(TAG, "Request " + client + "(" + version + "): " + method + " " + endpoint);
            for (Map.Entry<String, String> header: headers.entrySet()) {
                Log.p(TAG, "  Header " + header.getKey() + ": " + header.getValue());
            }

            switch (method) {
                case GET:
                    reply = getDispatcher.handleRequest(client, version, endpoint);
                    break;
                case POST:
                    reply = postDispatcher.handleRequest(
                        client,
                        version,
                        endpoint,
                        contentType,
                        session.getInputStream());
                    break;
                default:
                    throw new ClientError("Unimplemented method: " + method);
            }

            resp = new SafeResponse(Status.OK, reply);
        }
        catch (ClientError err) {
            Log.err(TAG, "Client error", err);
            resp = handleError(reply, Status.BAD_REQUEST, err);
        }
        catch (ServerError err) {
            Log.err(TAG, "Server error", err);
            resp = handleError(reply, Status.INTERNAL_ERROR, err);
        }
        catch (Exception err) {
            Log.err(TAG, "Internal Server error", err);
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
            Log.err(TAG, "Catastrophic server failure", e);
            return Response.newFixedLengthResponse(Status.INTERNAL_ERROR, "text/plain", err.toString());
        }
    }
}
