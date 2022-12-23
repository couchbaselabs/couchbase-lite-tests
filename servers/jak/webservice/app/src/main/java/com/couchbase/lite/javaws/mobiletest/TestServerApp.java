package com.couchbase.lite.javaws.mobiletest;

import androidx.annotation.NonNull;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintWriter;
import java.io.StringWriter;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicReference;

import javax.servlet.annotation.WebServlet;
import javax.servlet.http.HttpServlet;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import com.couchbase.lite.internal.utils.StringUtils;
import com.couchbase.lite.mobiletest.Args;
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
    public void init() {
        TestApp.init(new JavaWSTestApp(getServletContext().getServerInfo().replaceAll("\\s+", "_")));
        MEMORY.compareAndSet(null, Memory.create(TestApp.getApp().getAppId()));
    }

    protected void doPost(HttpServletRequest request, HttpServletResponse response) throws IOException {
        try {
            final Reply reply = dispatchRequest(request.getRequestURI(), request.getInputStream());
            final InputStream data = reply.getData();

            response.setStatus(HttpServletResponse.SC_OK);
            response.setHeader("Content-Type", reply.getContentType());
            response.setHeader("Content-Length", String.valueOf(reply.size()));

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

            final StringWriter sw = new StringWriter();
            e.printStackTrace(new PrintWriter(sw));

            response.getWriter().println(sw);
        }
    }

    /**
     * GET method, for testing
     */
    protected void doGet(HttpServletRequest request, HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setHeader("Content-Type", "text/plain");
        response.getOutputStream().write(CBL_OK);
        response.getOutputStream().flush();
        response.getOutputStream().close();
    }

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @NonNull
    private Reply dispatchRequest(@NonNull String req, @NonNull InputStream body) throws Exception {
        Log.i(TAG, "Request: " + req);

        final String[] path = req.split("/");
        final int pathLen = path.length;

        final String method = (pathLen <= 0) ? null : path[pathLen - 1];
        if (StringUtils.isEmpty(method)) { throw new IllegalArgumentException("Empty request"); }

        // Find and invoke the method on the RequestHandler.
        return TestApp.getApp().getDispatcher().run(req, Args.parse(body), MEMORY.get());
    }
}
