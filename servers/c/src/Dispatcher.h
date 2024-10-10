#pragma once

// cbl
#include "CBLManager.h"
#include "SessionManager.h"

// lib
#include <functional>
#include <string>
#include <vector>

struct mg_connection;

namespace ts {
    class Request;

    class TestServer;

    class Dispatcher {
    public:
        explicit Dispatcher(const TestServer *testServer);

        int handle(mg_connection *conn) const;

    private:
        using Handler = std::function<int(Request &request, Session *session)>;
        struct Rule {
            std::string method;
            std::string path;
            Handler handler;
        };

        void addRule(const Rule &rule);

        [[nodiscard]] Handler findHandler(const Request &request) const;

        // Handler Functions:

        int handleGETRoot(Request &request, Session *session);

        int handlePOSTReset(Request &request, Session *session);

        int handlePOSTNewSession(Request &request, Session *session);

        int handlePOSTGetAllDocuments(Request &request, Session *session);

        int handlePOSTUpdateDatabase(Request &request, Session *session);

        int handlePOSTStartReplicator(Request &request, Session *session);

        int handlePOSTStopReplicator(Request &request, Session *session);

        int handlePOSTGetReplicatorStatus(Request &request, Session *session);

        int handlePOSTSnapshotDocuments(Request &request, Session *session);

        int handlePOSTVerifyDocuments(Request &request, Session *session);

        int handlePOSTPerformMaintenance(Request &request, Session *session);

        int handlePOSTRunQuery(Request &request, Session *session);

        // Handler Functions for Testing:
        int handlePOSTGetDocument(Request &request, Session *session);

        // Member Variables:
        const TestServer *_testServer{nullptr};
        std::vector<Rule> _rules;
        std::unique_ptr<ts::SessionManager> _sessionManager;
    };
}