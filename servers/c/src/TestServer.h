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
        static constexpr unsigned short PORT = 8080;

        struct Context {
            std::string databaseDir;
            std::string assetsDir;
        };

        static void init();

        explicit TestServer();

        ~TestServer();

        TestServer(const TestServer &server) = delete;

        TestServer &operator=(const TestServer &server) = delete;

        [[nodiscard]] const Context &context() const { return _context; }

        [[nodiscard]] std::string serverUUID() const { return _uuid; }

        SessionManager *sessionManager() const { return _sessionManager.get(); }

        cbl::CBLManager *cblManager() const { return _cblManager.get(); }

        void start();

        void stop();

    private:
        int handleRequest(mg_connection *conn);

        Context _context;

        std::unique_ptr<ts::Dispatcher> _dispatcher;
        std::unique_ptr<ts::SessionManager> _sessionManager;
        std::unique_ptr<ts::cbl::CBLManager> _cblManager;

        mg_context *_server{nullptr};
        std::string _uuid;
    };
}