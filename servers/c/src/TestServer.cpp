#include "TestServer.h"
#include "Dispatcher.h"
#include <civetweb.h>
#include <string>

using namespace std;

TestServer::TestServer() {
    _context = nullptr;
    _dispatcher = Dispatcher();
}

void TestServer::start() {
    if (_context) {
        throw std::runtime_error("Already Started");
    }

    string port_str = to_string(PORT);
    const char* options[3] = {"listening_ports", port_str.c_str(), nullptr};

    _context = mg_start(nullptr, nullptr, options);

    mg_set_request_handler(_context, "/*", [](mg_connection *conn, void *context) -> int {
        auto server = static_cast<TestServer *>(context);
        return server->handleRequest(conn);
    }, this);
}

void TestServer::stop() {
    if (_context) {
        mg_stop(_context);
    }
}

int TestServer::handleRequest(mg_connection *conn) {
    return _dispatcher.handle(conn);
}
