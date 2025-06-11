#include "SessionManager.h"
#include "CBLManager.h"
#include "TestServer.h"

namespace ts {
    std::shared_ptr<Session> SessionManager::createSession(const std::string &id,
                                                           const std::string &datasetVersion) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_sessions.find(id) != _sessions.end()) {
            throw support::error::RequestError("Session with given ID already exists");
        }

        // Only have one session at least for now
        _sessions.clear();

        // Create CBLManager per session:
        auto context = _testServer->context();
        auto cblManager = std::make_unique<cbl::CBLManager>(
            context.databaseDir, context.assetsDir, datasetVersion);

        // Create session:
        auto session = std::make_shared<Session>(id, std::move(cblManager));
        _sessions.emplace(id, session);
        return session;
    }

    std::shared_ptr<Session> SessionManager::createTempSession() {
        return std::make_shared<Session>(support::key::generateUUID(), nullptr);
    }

    std::shared_ptr<Session> SessionManager::getSession(const std::string &id) const {
        std::lock_guard<std::mutex> lock(_mutex);
        auto it = _sessions.find(id);
        if (it == _sessions.end()) {
            throw support::error::RequestError("Session not found");
        }
        return it->second;
    }
}