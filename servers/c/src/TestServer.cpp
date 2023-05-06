#include "TestServer.h"
#include <civetweb.h>
#include <string>

using namespace std;

const TestServer::Context *TestServer::context() const {
    return &_context;
}

void TestServer::start() {
    if (_server) {
        throw std::runtime_error("Already Started");
    }

    string port_str = to_string(PORT);
    const char *options[3] = {"listening_ports", port_str.c_str(), nullptr};

    _server = mg_start(nullptr, nullptr, options);

    mg_set_request_handler(_server, "/*", [](mg_connection *conn, void *context) -> int {
        auto server = static_cast<TestServer *>(context);
        return server->handleRequest(conn);
    }, this);
}

void TestServer::stop() {
    if (_server) {
        mg_stop(_server);
    }
}

int TestServer::handleRequest(mg_connection *conn) {
    return _dispatcher.handle(conn);
}

