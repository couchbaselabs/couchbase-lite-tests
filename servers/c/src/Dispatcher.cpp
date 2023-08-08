#include "Dispatcher.h"
#include "Request.h"
#include "TestServer.h"

// support
#include "Error.h"
#include "Log.h"

// lib
#include <nlohmann/json.hpp>

using namespace nlohmann;
using namespace std;

using namespace ts::cbl;
using namespace ts::support::logger;
using namespace ts::support::error;

#define HANDLER(h) [this](Request& request) -> int { return h(request); }

namespace ts {
    Dispatcher::Dispatcher(const TestServer *testServer) {
        _testServer = testServer;
        _cblManager = make_unique<CBLManager>(_testServer->context().databaseDir, _testServer->context().assetsDir);

        addRule({"GET", "/", HANDLER(handleGETRoot)});
        addRule({"POST", "/reset", HANDLER(handlePOSTReset)});
        addRule({"POST", "/getAllDocuments", HANDLER(handlePOSTGetAllDocuments)});
        addRule({"POST", "/updateDatabase", HANDLER(handlePOSTUpdateDatabase)});
        addRule({"POST", "/startReplicator", HANDLER(handlePOSTStartReplicator)});
        addRule({"POST", "/getReplicatorStatus", HANDLER(handlePOSTGetReplicatorStatus)});
        addRule({"POST", "/snapshotDocuments", HANDLER(handlePOSTSnapshotDocuments)});
        addRule({"POST", "/verifyDocuments", HANDLER(handlePOSTVerifyDocuments)});

        // For testing:
        addRule({"POST", "/test/getDocument", HANDLER(handlePOSTGetDocument)});
    }

    int Dispatcher::handle(mg_connection *conn) const {
        Request request = Request(conn, _testServer);
        try {
            log(LogLevel::info, "Request %s", request.name().c_str());
            if (request.path() != "/") {
                if (request.version() != TestServer::API_VERSION) {
                    return request.respondWithServerError("API Version Mismatched or Missing");
                }

                if (request.clientID().empty()) {
                    return request.respondWithServerError("Client ID Missing");
                }
            }
            auto handler = findHandler(request);
            if (!handler) {
                return request.respondWithServerError("Request API Not Found");
            }
            return handler(request);
        } catch (const CBLException &e) {
            return request.respondWithCBLError(e);
        } catch (const RequestError &e) {
            return request.respondWithRequestError(e.what());
        } catch (const json::exception &e) {
            return request.respondWithRequestError(e.what());
        } catch (const std::logic_error &e) {
            return request.respondWithRequestError(e.what());
        } catch (const std::exception &e) {
            return request.respondWithServerError(e.what());
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
}