package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;

import java.io.PrintWriter;
import java.io.StringWriter;
import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

import org.nanohttpd.protocols.http.IHTTPSession;
import org.nanohttpd.protocols.http.NanoHTTPD;
import org.nanohttpd.protocols.http.request.Method;
import org.nanohttpd.protocols.http.response.Response;
import org.nanohttpd.protocols.http.response.Status;

import com.couchbase.lite.mobiletest.util.Log;
import com.couchbase.lite.mobiletest.util.StringUtils;


public class Server extends NanoHTTPD {
    private static final String TAG = "SERVER";

    private static final int PORT = 8080;
    private static final String KEY_POST_DATA = "postData";

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

    @NonNull
    @Override
    public Response handle(@NonNull IHTTPSession session) {
        int version = 1;
        Response resp;
        try {
            final Map<String, String> headers = session.getHeaders();

            try { version = Integer.parseInt(headers.get(TestApp.HEADER_PROTOCOL_VERSION)); }
            catch (NumberFormatException ignore) { }

            String client = headers.get(TestApp.HEADER_SENDER);
            if (client == null) { client = TestApp.DEFAULT_CLIENT; }

            String req = session.getUri();
            if (StringUtils.isEmpty(req)) { throw new IllegalArgumentException("Empty request"); }

            if (!req.startsWith("/")) { req = req.substring(1); }

            final Dispatcher.Method method = METHODS.get(session.getMethod());
            if (method == null) { throw new IllegalArgumentException("Unimplemented method: " + session.getMethod()); }

            Log.i(TAG, "Request(" + version + ")@" + client + " " + method + ":" + req);

            // Find and invoke the method on the RequestHandler.
            final Reply reply = dispatcher.run(version, client, method, req, session.getInputStream());

            resp = Response.newFixedLengthResponse(
                Status.OK,
                reply.getContentType(),
                reply.getData(),
                reply.size());
        }
        catch (Exception e) {
            Log.w(TAG, "Request failed", e);
            final StringWriter sw = new StringWriter();
            final PrintWriter pw = new PrintWriter(sw);
            e.printStackTrace(pw);
            resp = Response.newFixedLengthResponse(Status.BAD_REQUEST, "text/plain", sw.toString());
        }

        resp.addHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
        resp.addHeader(TestApp.HEADER_SENDER, appId);

        return resp;
    }
}
