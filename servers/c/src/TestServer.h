#pragma once

#include "Dispatcher.h"

struct mg_context;
struct mg_connection;

class TestServer {
public:
    static constexpr unsigned short PORT = 8080;

    struct Context {
        std::string databaseDir;
        std::string assetDir;
    };

    TestServer(Context context) : _context(context), _dispatcher(this) {}

    const Context *context() const;

    void start();

    void stop();

private:
    int handleRequest(mg_connection *conn);

    Context _context;
    mg_context *_server{nullptr};
    Dispatcher _dispatcher;
};
