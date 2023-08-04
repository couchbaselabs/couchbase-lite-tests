#include "TestServer.h"
#include <civetweb.h>
#include <string>

#ifdef __ANDROID__
#include "support/Android.h"
#endif

#include "support/Exception.h"
#include "support/Files.h"
#include "support/UUID.h"

using namespace std;
using namespace ts_support::exception;
using namespace ts_support::files;

#ifdef __ANDROID__
using namespace ts_support::android;
#endif

TestServer::TestServer() {
#ifdef __ANDROID__
    CheckNotNull(androidContext(), "Android Context is not initialized");
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

    _uuid = ts_support::key::generateUUID();

    string port_str = to_string(PORT);
    const char *options[3] = {"listening_ports", port_str.c_str(), nullptr};
    _server = mg_start(nullptr, nullptr, options);
    CheckNotNull(_server, "Cannot start server");

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
