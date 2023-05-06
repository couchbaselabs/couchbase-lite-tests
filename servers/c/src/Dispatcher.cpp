#include "Dispatcher.h"
#include "Common.h"
#include "Request.h"
#include "TestServer.h"

#define HANDLER(h) [this](Request& request) -> int { return h(request); }

Dispatcher::Dispatcher(const TestServer *testServer) {
    _testServer = testServer;
    _dbManager = make_unique<CBLManager>(_testServer->context()->databaseDir, _testServer->context()->assetDir);

    addRule({1, "GET", "/", HANDLER(handleGETRoot)});
    addRule({1, "POST", "/reset", HANDLER(handlePOSTReset)});
    addRule({1, "POST", "/getAllDocumentIDs", HANDLER(handlePOSTGetAllDocumentIDs)});
    addRule({1, "POST", "/startReplicator", HANDLER(handlePOSTStartReplicator)});
    addRule({1, "POST", "/getReplicatorStatus", HANDLER(handlePOSTGetReplicatorStatus)});
}

int Dispatcher::handle(mg_connection *conn) const {
    Request request = Request(conn);
    auto handler = findHandler(request);
    if (!handler) {
        return request.respondWithError(405);
    }

    try {
        return handler(request);
    } catch (const exception &e) {
        return request.respondWithError(400, e.what());
    }
}

void Dispatcher::addRule(const Rule &rule) {
    _rules.push_back(rule);
}

Dispatcher::Handler Dispatcher::findHandler(const Request &request) const {
    for (auto &rule: _rules) {
        if (rule.version <= request.version() &&
            rule.method == request.method() &&
            rule.path == request.path()) {
            return rule.handler;
        }
    }
    return nullptr;
}
