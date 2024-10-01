#pragma once

// cbl
#include "CBLManager.h"

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
        using Handler = std::function<int(Request &request)>;
        struct Rule {
            std::string method;
            std::string path;
            Handler handler;
        };

        void addRule(const Rule &rule);

        [[nodiscard]] Handler findHandler(const Request &request) const;

        // Handler Functions:

        int handleGETRoot(Request &request);

        int handlePOSTReset(Request &request);

        int handlePOSTGetAllDocuments(Request &request);

        int handlePOSTUpdateDatabase(Request &request);

        int handlePOSTStartReplicator(Request &request);

        int handlePOSTStopReplicator(Request &request);

        int handlePOSTGetReplicatorStatus(Request &request);

        int handlePOSTSnapshotDocuments(Request &request);

        int handlePOSTVerifyDocuments(Request &request);

        int handlePOSTPerformMaintenance(Request &request);

        int handlePOSTRunQuery(Request &request);

        // Handler Functions for Testing:
        int handlePOSTGetDocument(Request &request);

        // Member Variables:
        const TestServer *_testServer{nullptr};
        std::vector<Rule> _rules;
        std::unique_ptr<ts::cbl::CBLManager> _cblManager;
    };
}