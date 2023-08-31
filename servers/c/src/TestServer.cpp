#include "TestServer.h"

// support
#ifdef __ANDROID__
#include "Android.h"
#endif

#include "Files.h"
#include "Log.h"
#include "UUID.h"

// lib
#include <civetweb.h>
#include <string>

using namespace std;
using namespace ts::support;
using namespace ts::support::files;
using namespace ts::support::key;

#ifdef __ANDROID__
using namespace ts::support::android;
#endif

static bool sTestServerInitialized = false;

namespace ts {
    void TestServer::init() {
        if (sTestServerInitialized) { return; }

        logger::init(logger::LogLevel::info);
        mg_init_library(0);
        sTestServerInitialized = true;
    }

    TestServer::TestServer() {
        if (!sTestServerInitialized) {
            throw runtime_error("TestServer::init() hasn't been called");
        }

#ifdef __ANDROID__
        if (!androidContext()) { throw runtime_error("Android Context is not initialized"); }
#endif
        _context = {filesDir("CBL-C-TestServer", true), assetsDir()};
        _dispatcher = new Dispatcher(this);
    }

    TestServer::~TestServer() {
        stop();
        delete _dispatcher;
    }

    void TestServer::start() {
        if (_server) {
            return;
        }

        _uuid = generateUUID();

        string port_str = to_string(PORT);
        const char *options[3] = {"listening_ports", port_str.c_str(), nullptr};
        _server = mg_start(nullptr, nullptr, options);
        if (!_server) { throw runtime_error("Cannot start server"); }

        mg_set_request_handler(_server, "/*", [](mg_connection *conn, void *context) -> int {
            auto server = static_cast<TestServer *>(context);
            return server->handleRequest(conn);
        }, this);
    }

    void TestServer::stop() {
        if (_server) {
            mg_stop(_server);
            _server = nullptr;
        }
    }

    int TestServer::handleRequest(mg_connection *conn) {
        return _dispatcher->handle(conn);
    }
}
