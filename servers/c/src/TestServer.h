#pragma once

#include "Dispatcher.h"

#include <string>

struct mg_context;
struct mg_connection;

namespace ts {
    class TestServer {
    public:
        static constexpr const char *CBL_PLATFORM_NAME = "couchbase-lite-c";
        static constexpr unsigned short API_VERSION = 1;
        static constexpr unsigned short PORT = 8080;

        struct Context {
            std::string databaseDir;
            std::string assetsDir;
        };

        explicit TestServer();

        ~TestServer();

        TestServer(const TestServer &server) = delete;

        TestServer &operator=(const TestServer &server) = delete;

        [[nodiscard]] const Context &context() const { return _context; }

        [[nodiscard]] std::string serverUUID() const { return _uuid; }

        void start();

        void stop();

    private:
        int handleRequest(mg_connection *conn);

        Context _context;
        Dispatcher *_dispatcher{nullptr};
        mg_context *_server{nullptr};
        std::string _uuid;
    };
}