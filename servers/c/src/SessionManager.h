#pragma once

// cbl
#include "CBLManager.h"
#include "Error.h"
#include "UUID.h"

// lib
#include <string>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <utility>

namespace ts {
    class TestServer;

    class Session {
    public:
        Session(std::string  id, std::unique_ptr<ts::cbl::CBLManager> cblManager)
        : _id(std::move(id))
        , _cblManager(std::move(cblManager))
        { }

        [[nodiscard]]
        const std::string &id() const { return _id; }

        [[nodiscard]]
        ts::cbl::CBLManager *cblManager() const { return _cblManager.get(); }

    private:
        std::string _id;
        std::unique_ptr<ts::cbl::CBLManager> _cblManager;
    };

    class SessionManager {
    public:
        explicit SessionManager(const TestServer* testServer)
        : _testServer(testServer)
        { }

        std::shared_ptr<Session> createSession(const std::string &id, const std::string &datasetVersion);

        std::shared_ptr<Session> createTempSession();

        std::shared_ptr<Session> getSession(const std::string &id) const;

    private:
        mutable std::mutex _mutex;
        const TestServer *_testServer{nullptr};
        std::unordered_map<std::string, std::shared_ptr<Session>> _sessions;
    };
}