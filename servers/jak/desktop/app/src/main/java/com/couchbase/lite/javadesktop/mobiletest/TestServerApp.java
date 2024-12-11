package com.couchbase.lite.javadesktop.mobiletest;

import androidx.annotation.GuardedBy;

import java.io.FileWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.net.URI;
import java.util.Locale;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

import edu.umd.cs.findbugs.annotations.Nullable;
import edu.umd.cs.findbugs.annotations.SuppressFBWarnings;
import org.apache.commons.daemon.Daemon;
import org.apache.commons.daemon.DaemonContext;

import com.couchbase.lite.mobiletest.Server;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.errors.ServerError;
import com.couchbase.lite.mobiletest.services.Log;
import com.couchbase.lite.mobiletest.util.NetUtils;


public class TestServerApp implements Daemon {
    private static final String TAG = "MAIN";

    private static final AtomicReference<TestServerApp> APP = new AtomicReference<>();
    private static final AtomicReference<Server> SERVER = new AtomicReference<>();

    private static final Object LOCK = new Object();

    @Nullable
    @GuardedBy("LOCK")
    private static CountDownLatch stopLatch;

    /**
     * Main method runs as non-service mode for debugging use
     *
     * @param args cli args
     */
    @SuppressWarnings({"PMD.SystemPrintln", "RegexpSinglelineJava"})
    public static void main(String[] args) {
        startApp();

        if ((args.length > 0) && ("server".equals(args[0]))) {
            Runtime.getRuntime().addShutdownHook(new Thread(TestServerApp::stopApp));
            waitForStop();
        }
        else {
            // Here if running interactively
            System.out.print("Hit Enter to stop >>> ");
            try { System.in.read(); }
            catch (IOException err) { Log.err(TAG, "Exception waiting for CLI input", err); }
            stopApp();
        }
    }

    /**
     * Static methods called by prunsrv to start/stop the Windows service.
     * Pass the argument "start" to start the service and any other argument to stop it.
     *
     * @param args Arguments from prunsrv command line
     **/
    @SuppressWarnings("PMD.MissingBreakInSwitch")
    public static void windowsService(String[] args) {
        switch (args[0].trim().toLowerCase(Locale.getDefault())) {
            case "":
            case "start":
                startApp();
                waitForStop();
                break;

            default:
                stopApp();
        }
    }

    private static void startApp() {
        final TestServerApp app = new TestServerApp();
        if (!APP.compareAndSet(null, app)) { throw new ServerError("Attempt to restart app"); }

        app.initApp();

        app.start();
    }

    @SuppressFBWarnings("UW_UNCOND_WAIT")
    private static void waitForStop() {
        while ((SERVER.get()) != null) {
            synchronized (LOCK) { stopLatch = new CountDownLatch(1); }
            try { stopLatch.await(); }
            catch (InterruptedException ignore) { }
        }
    }

    private static void stopApp() {
        final TestServerApp app = APP.getAndSet(null);
        if (app != null) { app.stop(); }
    }


    @Override
    public void init(DaemonContext context) { initApp(); }

    @SuppressFBWarnings("DM_DEFAULT_ENCODING")
    @Override
    public void start() {
        final Server server = new Server();
        if (!SERVER.compareAndSet(null, server)) { throw new ServerError("Attempt to restart server"); }

        final String addr = NetUtils.getLocalAddress();
        if (addr == null) { throw new ServerError("Cannot get server address"); }

        final URI serverUri = NetUtils.makeUri("http", addr, server.myPort, "");
        if (serverUri == null) { throw new ServerError("Cannot get server URI"); }

        try (PrintWriter writer = new PrintWriter(new FileWriter("server.url"))) { writer.println(serverUri); }
        catch (IOException e) { throw new ServerError("Failed to write server URI to file", e); }

        try { server.start(); }
        catch (IOException e) { throw new ServerError("Failed to start server", e); }
        Log.p(TAG, "Java Desktop Test Server running at " + serverUri);
    }

    @SuppressFBWarnings("NN_NAKED_NOTIFY")
    @Override
    public void stop() {
        final Server server = SERVER.getAndSet(null);
        if (server != null) { server.stop(); }

        synchronized (LOCK) {
            if (stopLatch != null) { stopLatch.countDown(); }
        }

        Log.p(TAG, "Java Desktop Test Server Stopped.");
    }

    @Override
    public void destroy() { Log.p(TAG, "TestServer service is destroyed."); }

    private void initApp() {
        TestApp.init(new JavaDesktopTestApp());
        Log.p(TAG, "Java Desktop Test Server " + TestApp.getApp().getAppId());
    }
}
