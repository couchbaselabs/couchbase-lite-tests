#pragma once

#include "CBLManager.h"
#include <functional>

struct mg_connection;

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

    int handlePOSTGetAllDocumentIDs(Request &request);

    int handlePOSTUpdateDatabase(Request &request);

    int handlePOSTStartReplicator(Request &request);

    int handlePOSTGetReplicatorStatus(Request &request);

    // Handler Functions for Testing:
    int handlePOSTGetDocument(Request &request);

    // Member Variables:
    const TestServer *_testServer{nullptr};
    std::vector<Rule> _rules;
    std::unique_ptr<CBLManager> _cblManager;
};
