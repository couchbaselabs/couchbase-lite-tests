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
import com.couchbase.lite.mobiletest.GetDispatcher;
import com.couchbase.lite.mobiletest.PostDispatcher;
import com.couchbase.lite.mobiletest.Reply;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.errors.ClientError;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.errors.TestError;
import com.couchbase.lite.mobiletest.tools.ErrorBuilder;
import com.couchbase.lite.mobiletest.tools.ReplyBuilder;
import com.couchbase.lite.mobiletest.util.Log;


@WebServlet(name = "TestServerApp", urlPatterns = {"/"}, loadOnStartup = 1)
public class TestServerApp extends HttpServlet {
    private static final String TAG = "MAIN";

    private enum Method {UNKNOWN, GET, POST}

    // Servlets are serializable...
    private static final long serialVersionUID = 42L;

    private transient GetDispatcher getDispatcher;
    private transient PostDispatcher postDispatcher;

    @Override
    public void init() {
        final TestApp app = new JavaWSTestApp();
        TestApp.init(app);
        getDispatcher = new GetDispatcher(app);
        postDispatcher = new PostDispatcher(app);
    }

    protected void doGet(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Method.GET, req, resp);
    }

    @Override
    protected void doPut(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Method.UNKNOWN, req, resp);
    }

    protected void doPost(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Method.POST, req, resp);
    }

    @Override
    protected void doDelete(HttpServletRequest req, HttpServletResponse resp) {
        dispatchRequest(Method.UNKNOWN, req, resp);
    }

    @SuppressWarnings({"PMD.PreserveStackTrace", "PMD.NPathComplexity", "PMD.ExceptionAsFlowControl"})
    private void dispatchRequest(Method method, HttpServletRequest req, HttpServletResponse resp) {
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

            final String client = req.getHeader(TestApp.HEADER_CLIENT);
            Log.i(TAG, "Request " + client + "(" + version + "): " + method + " " + endpoint);
            Reply reply = null;
            try {
                switch (method) {
                    case GET:
                        reply = getDispatcher.handleRequest(client, version, endpoint);
                        break;
                    case POST:
                        reply = postDispatcher.handleRequest(client, version, endpoint, req.getInputStream());
                        break;
                    default:
                        throw new ClientError("Unimplemented method: " + method);
                }

                resp.setHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
                resp.setHeader(TestApp.HEADER_SERVER, TestApp.getApp().getAppId());
                buildResponse(reply, resp);

                resp.setStatus(HttpServletResponse.SC_OK);

                resp.setHeader("Content-Type", "application/json");
                resp.setHeader("Content-Length", String.valueOf(reply.getSize()));
            }
            finally {
                if (reply != null) { reply.close(); }
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
