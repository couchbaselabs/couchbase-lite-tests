#pragma once

#include "Dispatcher.h"

struct mg_context;
struct mg_connection;

class TestServer {
public:
    static constexpr const char *CBL_PLATFORM_NAME = "couchbase-lite-c";
    static constexpr const char *VERSION = "3.1.0";
    static constexpr unsigned short API_VERSION = 1;
    static constexpr unsigned short PORT = 8080;

    struct Context {
        std::string databaseDir;
        std::string assetDir;
    };

    explicit TestServer(Context context) : _context(std::move(context)), _dispatcher(this) {}

    [[nodiscard]] const Context *context() const { return &_context; }

    std::string serverUUID() const { return _uuid; }

    void start();

    void stop();

private:
    int handleRequest(mg_connection *conn);

    Context _context;
    mg_context *_server{nullptr};
    Dispatcher _dispatcher;
    std::string _uuid;
};
