package com.couchbase.lite.javaws.mobiletest;

import androidx.annotation.NonNull;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import com.couchbase.lite.internal.utils.StringUtils;
import com.couchbase.lite.mobiletest.Dispatcher;
import com.couchbase.lite.mobiletest.Reply;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.errors.TestError;
import com.couchbase.lite.mobiletest.util.Log;


@WebServlet(name = "TestServerApp", urlPatterns = {"/"}, loadOnStartup = 1)
public class TestServerApp extends HttpServlet {
    private static final String TAG = "MAIN";

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
    private void dispatchRequest(Dispatcher.Method method, HttpServletRequest req, HttpServletResponse resp) {
        final TestApp app = TestApp.getApp();
        int version = TestApp.DEFAULT_PROTOCOL_VERSION;
        try {
            final String versionStr = req.getHeader(TestApp.HEADER_PROTOCOL_VERSION);
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

            String client = req.getHeader(TestApp.HEADER_CLIENT);
            if (client == null) {
                client = TestApp.DEFAULT_CLIENT;
                Log.w(TAG, "Request does not specify a client Id. Using " + client);
            }

            final String endpoint = req.getRequestURI();
            if (StringUtils.isEmpty(endpoint)) { throw new IllegalArgumentException("Empty request"); }

            Log.i(TAG, "Request " + client + "(" + version + "): " + method + " " + endpoint);

            resp.setHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
            resp.setHeader(TestApp.HEADER_SERVER, app.getAppId());

            final Dispatcher dispatcher = app.getDispatcher();
            try (Reply reply = dispatcher.handleRequest(client, version, method, endpoint, req.getInputStream())) {
                try (InputStream in = reply.getContent(); OutputStream out = resp.getOutputStream()) {
                    final byte[] buf = new byte[1024];
                    while (true) {
                        final int n = in.read(buf, 0, buf.length);
                        if (n <= 0) { break; }
                        out.write(buf, 0, n);
                    }
                    out.flush();
                }

                resp.setStatus(HttpServletResponse.SC_OK);

                resp.setHeader("Content-Type", "application/json");
                resp.setHeader("Content-Length", String.valueOf(reply.getSize()));
            }
        }
        catch (ClientError err) {
            Log.w(TAG, "Client error", err);
            handleError(HttpServletResponse.SC_BAD_REQUEST, err, resp);
        }
        catch (ServerError err) {
            Log.w(TAG, "Server error", err);
            handleError(HttpServletResponse.SC_INTERNAL_SERVER_ERROR, err, resp);
        }
        catch (Exception err) {
            Log.w(TAG, "Internal Server error", err);
            handleError(
                HttpServletResponse.SC_INTERNAL_SERVER_ERROR,
                new ServerError("Internal server error", err),
                resp);
        }
    }

    private void handleError(int status, @NonNull TestError err, @NonNull HttpServletResponse resp) {
        resp.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
        resp.setHeader("Content-Type", "text/plain");
        try { resp.getWriter().println(err.printError()); }
        catch (IOException e) { Log.e(TAG, "Failed writing error to response", e); }
    }
}
