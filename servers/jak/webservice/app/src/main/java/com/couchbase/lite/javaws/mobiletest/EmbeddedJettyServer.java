package com.couchbase.lite.javaws.mobiletest;

import org.eclipse.jetty.server.Server;
import org.eclipse.jetty.servlet.ServletContextHandler;

public class EmbeddedJettyServer {
    public static void main(String[] args) throws Exception {
        // Create a basic Jetty server instance
        Server server = new Server(8080);

        // Set up a servlet context and map servlets
        ServletContextHandler context = new ServletContextHandler(ServletContextHandler.SESSIONS);
        context.setContextPath("/");
        server.setHandler(context);

        context.addServlet(TestServerApp.class, "/");

        // Start the server
        server.start();
        server.join();
    }
}