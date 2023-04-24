#pragma once
#include "Dispatcher.h"

struct mg_context;
struct mg_connection;

class TestServer {
public:
    static constexpr unsigned short PORT = 8080;

    TestServer();

    void start();
    void stop();

private:
    int handleRequest(mg_connection *conn);

    mg_context* _context;
    Dispatcher _dispatcher;
};
