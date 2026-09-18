#pragma once

#include "CBLManager.h"
#include "Dispatcher.h"
#include "SessionManager.h"

#include <string>
#include <memory>

struct mg_context;
struct mg_connection;

namespace ts {
    class TestServer {
    public:
        static constexpr const char *CBL_PLATFORM_NAME = "couchbase-lite-c";
        static constexpr unsigned short API_VERSION = 1;
        static constexpr unsigned short DEFAULT_PORT = 8080;

        struct Context {
            std::string filesDir;
            std::string assetsDir;
        };

        static void init();

        explicit TestServer(unsigned short port = DEFAULT_PORT);

        ~TestServer();

        TestServer(const TestServer &server) = delete;

        TestServer &operator=(const TestServer &server) = delete;

        [[nodiscard]] const Context &context() const { return _context; }

        [[nodiscard]] std::string serverUUID() const { return _uuid; }

        [[nodiscard]] unsigned short port() const { return _port; }

        SessionManager *sessionManager() const { return _sessionManager.get(); }

        void start();

        void stop();

    private:
        int handleRequest(mg_connection *conn);

        Context _context;

        std::unique_ptr<ts::Dispatcher> _dispatcher;
        std::unique_ptr<ts::SessionManager> _sessionManager;

        mg_context *_server{nullptr};
        unsigned short _port;
        std::string _uuid;
    };
}