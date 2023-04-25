#include "Dispatcher.h"
#include "Request.h"

using namespace std;
using namespace nlohmann;

#define HANDLER(h) [this](const Request& request) -> int { return h(request); }

Dispatcher::Dispatcher() {
    addRule({1, "GET", "/", HANDLER(handleGETRoot)});
}

int Dispatcher::handle(mg_connection *conn) const {
    Request request = Request(conn);
    auto handler = findHandler(request);
    if (!handler) {
        return request.respondWithError(405);
    }

    try {
        return handler(request);
    } catch(const exception& e) {
        string msg = "Exception caught during router handling: " + string(e.what());
        return request.respondWithError(405, msg.c_str());
    }
}

void Dispatcher::addRule(const Rule& rule) {
    _rules.push_back(rule);
}

Dispatcher::Handler Dispatcher::findHandler(const Request& request) const {
    for (auto &rule : _rules) {
        if (rule.version <= request.version() &&
            rule.method == request.method() &&
            rule.path == request.path()) {
            return rule.handler;
        }
    }
    return nullptr;
}

int Dispatcher::handleGETRoot(const Request& request) {
    json result;
    result["version"] = "3.1.0";
    result["apiVersion"] = 1;
    result["cbl"] = "couchbase-lite-c";
    return request.respondWithJSON(result);
}