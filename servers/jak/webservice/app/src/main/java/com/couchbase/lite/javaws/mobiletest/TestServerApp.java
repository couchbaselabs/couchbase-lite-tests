package com.couchbase.lite.javaws.mobiletest;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.concurrent.atomic.AtomicReference;

import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import com.couchbase.lite.internal.utils.StringUtils;
import com.couchbase.lite.mobiletest.Dispatcher;
import com.couchbase.lite.mobiletest.Reply;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.TestException;
import com.couchbase.lite.mobiletest.util.Log;


@WebServlet(name = "TestServerApp", urlPatterns = {"/"}, loadOnStartup = 1)
public class TestServerApp extends HttpServlet {
    private static final String TAG = "MAIN";

    private static final AtomicReference<String> CLIENT = new AtomicReference<>();

    // Servlets are serializable...
    private static final long serialVersionUID = 42L;

    @Override
    public void init() { TestApp.init(new JavaWSTestApp()); }

    protected void doGet(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Dispatcher.Method.GET, req, resp);
    }

    @Override
    protected void doPut(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Dispatcher.Method.PUT, req, resp);
    }

    protected void doPost(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Dispatcher.Method.POST, req, resp);
    }

    @Override
    protected void doDelete(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Dispatcher.Method.DELETE, req, resp);
    }

    @SuppressWarnings("PMD.PreserveStackTrace")
    private void dispatchRequest(Dispatcher.Method method, HttpServletRequest request, HttpServletResponse response) {
        final TestApp app = TestApp.getApp();
        int version = 0;
        try {
            final String versionStr = request.getHeader(TestApp.HEADER_PROTOCOL_VERSION);
            if (versionStr == null) { throw new IllegalArgumentException("Missing protocol version"); }
            try { version = Integer.parseInt(versionStr); }
            catch (NumberFormatException ignore) {
                throw new IllegalArgumentException("Unrecognized protocol version");
            }

            String client = request.getHeader(TestApp.HEADER_SENDER);
            if (client == null) { client = TestApp.DEFAULT_CLIENT; }

            final String previousClient = TestServerApp.CLIENT.getAndSet(client);
            if (!client.equals(previousClient)) { Log.w(TAG, "New client: " + previousClient + " => " + client); }

            final String endpoint = request.getRequestURI();
            if (StringUtils.isEmpty(endpoint)) { throw new IllegalArgumentException("Empty request"); }

            Log.i(TAG, "Request(" + version + ")@" + client + " " + method + ":" + endpoint);

            try (Reply reply
                     = app.getDispatcher().handleRequest(client, version, method, endpoint, request.getInputStream())) {
                response.setStatus(reply.getStatus().getCode());

                response.setHeader("Content-Type", reply.getContentType());
                response.setHeader("Content-Length", String.valueOf(reply.getSize()));

                response.setHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
                response.setHeader(TestApp.HEADER_SENDER, app.getAppId());

                try (InputStream in = reply.getContent(); OutputStream out = response.getOutputStream()) {
                    final byte[] buf = new byte[1024];
                    while (true) {
                        final int n = in.read(buf, 0, buf.length);
                        if (n <= 0) { break; }
                        out.write(buf, 0, n);
                    }
                    out.flush();
                }
            }
        }
        catch (IOException | RuntimeException err) {
            Log.w(TAG, "Server error", err);

            response.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            response.setHeader("Content-Type", "text/plain");
            try { response.getWriter().println(TestException.printError(err)); }
            catch (IOException e) { Log.e(TAG, "Failed writing error to response", e); }

            response.setHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
            response.setHeader(TestApp.HEADER_SENDER, app.getAppId());
        }
    }
}
