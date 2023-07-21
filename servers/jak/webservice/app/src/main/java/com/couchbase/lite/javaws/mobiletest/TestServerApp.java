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
import com.couchbase.lite.mobiletest.factories.ErrorBuilder;
import com.couchbase.lite.mobiletest.factories.ReplyBuilder;
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

    @SuppressWarnings({"PMD.PreserveStackTrace", "PMD.NPathComplexity"})
    private void dispatchRequest(Dispatcher.Method method, HttpServletRequest req, HttpServletResponse resp) {
        final TestApp app = TestApp.getApp();
        int version = -1;
        try {
            final String versionStr = req.getHeader(TestApp.HEADER_PROTOCOL_VERSION);
            if (versionStr != null) {
                try {
                    final int v = Integer.parseInt(versionStr);
                    if (TestApp.KNOWN_VERSIONS.contains(v)) { version = v; }
                }
                catch (NumberFormatException ignore) { }
            }

            final String endpoint = req.getRequestURI();
            if (StringUtils.isEmpty(endpoint)) { throw new ClientError("Empty request"); }

            String client = req.getHeader(TestApp.HEADER_CLIENT);
            Log.i(TAG, "Request " + client + "(" + version + "): " + method + " " + endpoint);

            // Special handling for the 'GET /' endpoint
            if ("/".equals(endpoint) && (Dispatcher.Method.GET.equals(method))) {
                if (version < 0) { version = TestApp.LATEST_SUPPORTED_PROTOCOL_VERSION; }
                if (client == null) { client = "anonymous"; }
            }

            if (version < 0) { throw new ClientError("No protocol version specified"); }
            if (client == null) { throw new ClientError("No client specified"); }

            resp.setHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
            resp.setHeader(TestApp.HEADER_SERVER, app.getAppId());

            final Dispatcher dispatcher = app.getDispatcher();
            try (Reply reply = dispatcher.handleRequest(client, version, method, endpoint, req.getInputStream())) {
                buildResponse(reply, resp);

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

    private static void buildResponse(@NonNull Reply reply, @NonNull HttpServletResponse resp) throws IOException {
        try (InputStream in = reply.getContent(); OutputStream out = resp.getOutputStream()) {
            final byte[] buf = new byte[1024];
            while (true) {
                final int n = in.read(buf, 0, buf.length);
                if (n <= 0) { break; }
                out.write(buf, 0, n);
            }
            out.flush();
        }
    }

    private void handleError(int status, @NonNull TestError err, @NonNull HttpServletResponse resp) {
        resp.setStatus(status);
        resp.setHeader("Content-Type", "application/json");

        try (Reply reply = new Reply(new ReplyBuilder(new ErrorBuilder(err).build()).buildReply())) {
            buildResponse(reply, resp);

            resp.setStatus(status);

            resp.setHeader("Content-Type", "application/json");
            resp.setHeader("Content-Length", String.valueOf(reply.getSize()));
        }
        catch (Exception e) {
            Log.w(TAG, "Catastrophic server failure", e);
            resp.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            resp.setHeader("Content-Type", "text/plain");
            try { resp.getWriter().println(err.getMessage()); }
            catch (IOException ioe) { Log.e(TAG, "Failed writing error to response", e); }
        }
    }
}
