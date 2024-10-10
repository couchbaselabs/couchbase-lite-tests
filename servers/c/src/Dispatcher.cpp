#include "Dispatcher.h"
#include "Request.h"
#include "TestServer.h"

// support
#include "Error.h"
#include "JSON.h"
#include "Log.h"

// lib
#include <nlohmann/json.hpp>

using namespace nlohmann;
using namespace std;

using namespace ts::cbl;
using namespace ts::support::logger;
using namespace ts::support::error;
using namespace ts::support::json_util;

#define HANDLER(h) [this](Request& request, Session* session) -> int { return h(request, session); }

// API Version : 0.6.0
// - No remote logging support yet
namespace ts {
    Dispatcher::Dispatcher(const TestServer *testServer) {
        _testServer = testServer;

        // We may change to have a manager per session with a different database directory
        // for each session in the future.
        auto manager = make_shared<CBLManager>(_testServer->context().databaseDir,
                                               _testServer->context().assetsDir);
        _sessionManager = make_unique<SessionManager>(manager);

        addRule({"GET", "/", HANDLER(handleGETRoot)});
        addRule({"POST", "/newSession", HANDLER(handlePOSTNewSession)});
        addRule({"POST", "/reset", HANDLER(handlePOSTReset)});
        addRule({"POST", "/getAllDocuments", HANDLER(handlePOSTGetAllDocuments)});
        addRule({"POST", "/test/getDocument", HANDLER(handlePOSTGetDocument)});
        addRule({"POST", "/updateDatabase", HANDLER(handlePOSTUpdateDatabase)});
        addRule({"POST", "/startReplicator", HANDLER(handlePOSTStartReplicator)});
        addRule({"POST", "/getReplicatorStatus", HANDLER(handlePOSTGetReplicatorStatus)});
        addRule({"POST", "/snapshotDocuments", HANDLER(handlePOSTSnapshotDocuments)});
        addRule({"POST", "/verifyDocuments", HANDLER(handlePOSTVerifyDocuments)});
        addRule({"POST", "/performMaintenance", HANDLER(handlePOSTPerformMaintenance)});
        addRule({"POST", "/runQuery", HANDLER(handlePOSTRunQuery)});
    }

    int Dispatcher::handle(mg_connection *conn) const {
        Request request = Request(conn, _testServer);
        try {
            log(LogLevel::info, "Request %s", request.name().c_str());
            if (request.path() != "/") {
                if (request.version() != TestServer::API_VERSION) {
                    return request.respondWithServerError("API Version Mismatched or Missing");
                }
            }

            shared_ptr<Session> session;
            if (request.path() == "/") {
                session = _sessionManager->createTempSession();
            } else if (request.path() == "/newSession") {
                json body = request.jsonBody();
                CheckBody(body);
                auto id = GetValue<string>(body, "id");
                session = _sessionManager->createSession(id);
            } else {
                auto id = request.clientID();
                if (id.empty()) {
                    return request.respondWithServerError("Client ID Missing");
                }
                session = _sessionManager->getSession(id);
            }

            auto handler = findHandler(request);
            if (!handler) {
                return request.respondWithServerError("Request API Not Found");
            }
            return handler(request, session.get());
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