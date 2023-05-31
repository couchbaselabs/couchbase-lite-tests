#include "Dispatcher.h"
#include "Common.h"
#include "Request.h"
#include "TestServer.h"

#define HANDLER(h) [this](Request& request) -> int { return h(request); }

Dispatcher::Dispatcher(const TestServer *testServer) {
    _testServer = testServer;
    _cblManager = make_unique<CBLManager>(_testServer->context()->databaseDir, _testServer->context()->assetDir);

    addRule({"GET", "/", HANDLER(handleGETRoot)});
    addRule({"POST", "/reset", HANDLER(handlePOSTReset)});
    addRule({"POST", "/getAllDocumentIDs", HANDLER(handlePOSTGetAllDocumentIDs)});
    addRule({"POST", "/updateDatabase", HANDLER(handlePOSTUpdateDatabase)});
    addRule({"POST", "/startReplicator", HANDLER(handlePOSTStartReplicator)});
    addRule({"POST", "/getReplicatorStatus", HANDLER(handlePOSTGetReplicatorStatus)});

    // For testing:
    addRule({"POST", "/test/getDocument", HANDLER(handlePOSTGetDocument)});
}

int Dispatcher::handle(mg_connection *conn) const {
    Request request = Request(conn, _testServer);
    try {
        if (request.path() != "/") {
            if (request.version() != TestServer::API_VERSION) {
                return request.respondWithError(403, "API Version Mismatched, Missing or Invalid Format");
            }

            if (request.clientUUID().empty()) {
                return request.respondWithError(403, "Client UUID Missing");
            }
        }
        
        auto handler = findHandler(request);
        if (!handler) {
            return request.respondWithError(404, "Request API Not Found");
        }

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
        if (rule.method == request.method() &&
            rule.path == request.path()) {
            return rule.handler;
        }
    }
    return nullptr;
}
