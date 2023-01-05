package com.couchbase.lite.javaws.mobiletest;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import javax.servlet.ServletException;
import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import com.couchbase.lite.internal.utils.StringUtils;
import com.couchbase.lite.mobiletest.Dispatcher;
import com.couchbase.lite.mobiletest.Memory;
import com.couchbase.lite.mobiletest.Reply;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.util.Log;


@WebServlet(name = "TestServerApp", urlPatterns = {"/"}, loadOnStartup = 1)
public class TestServerApp extends HttpServlet {
    private static final String TAG = "MAIN";
    private static final byte[] CBL_OK = "CouchbaseLite Java WebService - OK".getBytes(StandardCharsets.UTF_8);

    // Servlets are serializable...
    private static final long serialVersionUID = 42L;

    private static final AtomicReference<Memory> MEMORY = new AtomicReference<>();

    @Override
    public void init() { TestApp.init(new JavaWSTestApp()); }

    protected void doGet(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        dispatchRequest(Dispatcher.Method.GET, req, resp);
    }

    @Override
    protected void doPut(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        dispatchRequest(Dispatcher.Method.PUT, req, resp);
    }

    protected void doPost(HttpServletRequest req, HttpServletResponse resp) throws IOException {
        dispatchRequest(Dispatcher.Method.POST, req, resp);
    }

    @Override
    protected void doDelete(HttpServletRequest req, HttpServletResponse resp) throws ServletException, IOException {
        dispatchRequest(Dispatcher.Method.DELETE, req, resp);
    }

    private void dispatchRequest(Dispatcher.Method method, HttpServletRequest request, HttpServletResponse response)
        throws IOException {
        final TestApp app = TestApp.getApp();
        int version = 1;
        try {
            try { version = Integer.parseInt(request.getHeader(TestApp.HEADER_PROTOCOL_VERSION)); }
            catch (NumberFormatException ignore) { }

            String client = request.getHeader(TestApp.HEADER_SENDER);
            if (client == null) { client = TestApp.DEFAULT_CLIENT; }

            final String reqUri = request.getRequestURI();
            final String[] path = reqUri.split("/");
            final int pathLen = path.length;
            final String req = (pathLen <= 0) ? null : path[pathLen - 1];
            if (StringUtils.isEmpty(req)) { throw new IllegalArgumentException("Empty request"); }

            Log.i(TAG, "Request(" + version + ")@" + client + " " + method + ":" + req);

            final Reply reply = app.getDispatcher().run(version, client, method, req, request.getInputStream());

            final InputStream data = reply.getData();

            response.setStatus(HttpServletResponse.SC_OK);

            response.setHeader("Content-Type", reply.getContentType());
            response.setHeader("Content-Length", String.valueOf(reply.size()));

            response.setHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
            response.setHeader(TestApp.HEADER_SENDER, app.getAppId());

            final OutputStream out = response.getOutputStream();
            final byte[] buf = new byte[1024];
            while (true) {
                final int n = data.readNBytes(buf, 0, buf.length);
                if (n <= 0) { break; }
                out.write(buf, 0, n);
            }
            out.flush();
            out.close();
        }
        catch (Exception e) {
            Log.w(TAG, "Request failed", e);

            response.setStatus(HttpServletResponse.SC_INTERNAL_SERVER_ERROR);
            response.setHeader("Content-Type", "text/plain");

            response.setHeader(TestApp.HEADER_PROTOCOL_VERSION, String.valueOf(version));
            response.setHeader(TestApp.HEADER_SENDER, app.getAppId());

            final StringWriter sw = new StringWriter();
            e.printStackTrace(new PrintWriter(sw));

            response.getWriter().println(sw);
        }
    }
}
