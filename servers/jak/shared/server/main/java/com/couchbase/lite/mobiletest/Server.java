package com.couchbase.lite.mobiletest;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;

import java.io.InputStream;
import java.io.PrintWriter;
import java.io.StringWriter;

import org.nanohttpd.protocols.http.IHTTPSession;
import org.nanohttpd.protocols.http.NanoHTTPD;
import org.nanohttpd.protocols.http.response.Response;
import org.nanohttpd.protocols.http.response.Status;

import com.couchbase.lite.internal.utils.StringUtils;
import com.couchbase.lite.mobiletest.util.Log;


public class Server extends NanoHTTPD {
    private static final String TAG = "SERVER";

    private static final int PORT = 8080;
    private static final String KEY_POST_DATA = "postData";

    private final Memory memory;
    private final Dispatcher dispatcher;

    public Server(@NonNull String address) {
        super(PORT);
        this.memory = Memory.create(address);
        this.dispatcher = TestApp.getApp().getDispatcher();
    }

    @NonNull
    @Override
    public Response handle(@NonNull IHTTPSession session) {
        try {
            final Reply reply = dispatchRequest(session.getUri(), session.getInputStream());
            return Response.newFixedLengthResponse(Status.OK, reply.getContentType(), reply.getData(), reply.size());
        }
        catch (Exception e) {
            Log.w(TAG, "Request failed", e);
            final StringWriter sw = new StringWriter();
            final PrintWriter pw = new PrintWriter(sw);
            e.printStackTrace(pw);
            return Response.newFixedLengthResponse(Status.BAD_REQUEST, "text/plain", sw.toString());
        }
    }

    @SuppressWarnings("PMD.SignatureDeclareThrowsException")
    @NonNull
    private Reply dispatchRequest(@Nullable String req, @NonNull InputStream body) throws Exception {
        Log.i(TAG, "Request: " + req);

        if (StringUtils.isEmpty(req)) { throw new IllegalArgumentException("Empty request"); }

        if (!req.startsWith("/")) { req = req.substring(1); }

        // Find and invoke the method on the RequestHandler.
        return dispatcher.run(req, Args.parse(body), memory);
    }
}
