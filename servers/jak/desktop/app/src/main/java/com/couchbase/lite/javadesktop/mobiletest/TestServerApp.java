package com.couchbase.lite.javadesktop.mobiletest;

import java.io.IOException;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicReference;

import org.apache.commons.daemon.Daemon;
import org.apache.commons.daemon.DaemonContext;

import com.couchbase.lite.mobiletest.Server;
import com.couchbase.lite.mobiletest.TestApp;
import com.couchbase.lite.mobiletest.util.Log;


public class TestServerApp implements Daemon {
    private static final String TAG = "MAIN";

    private static final AtomicReference<TestServerApp> APP = new AtomicReference<>();
    private static final AtomicReference<Server> SERVER = new AtomicReference<>();

    /**
     * Main method runs as non-service mode for debugging use
     *
     * @param args cli args
     */
    @SuppressWarnings({"PMD.SystemPrintln", "RegexpSinglelineJava"})
    public static void main(String[] args) {
        startApp();

        System.out.print("Hit Enter to stop >>> ");
        try { System.in.read(); }
        catch (IOException err) { Log.w(TAG, "Exception waiting for CLI input", err); }

        stopApp();
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
                Server server;
                while ((server = SERVER.get()) != null) {
                    synchronized (server) {
                        try { server.wait(); }
                        catch (InterruptedException ignore) { }
                    }
                }
                return;

            default:
                stopApp();
        }
    }

    private static void startApp() {
        final TestServerApp app = new TestServerApp();

        if (!APP.compareAndSet(null, app)) { throw new IllegalStateException("Attempt to restart app"); }

        app.initApp();
        app.start();
    }

    private static void stopApp() {
        Log.i(TAG, "Stopping TestServer service.");
        final Server server = SERVER.getAndSet(null);
        if (server != null) {
            server.stop();
            synchronized (server) { server.notifyAll(); }
        }
        APP.set(null);
    }


    @Override
    public void init(DaemonContext context) { initApp(); }

    @Override
    public void start() {
        final String id = TestApp.getApp().getAppId();

        final Server server = new Server();
        if (!SERVER.compareAndSet(null, server)) { throw new IllegalStateException("Attempt to restart server"); }

        Log.i(TAG, "Server launched at " + id + ":" + server.myPort);
    }

    @Override
    public void stop() { stopApp(); }

    @Override
    public void destroy() { Log.i(TAG, "TestServer service is destroyed."); }

    private void initApp() {
        TestApp.init(new JavaDesktopTestApp());
        Log.i(TAG, "TestKit App initialized.");
    }
}
