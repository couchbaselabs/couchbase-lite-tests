#include "SessionManager.h"

namespace ts {

    std::shared_ptr<Session> SessionManager::createSession(const std::string &id) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_sessions.find(id) != _sessions.end()) {
            throw support::error::RequestError("Session with given ID already exists");
        }

        // Only have one session at least for now
        _sessions.clear();

        auto session = std::make_shared<Session>(id, _cblManager);
        _sessions.emplace(id, session);
        return session;
    }

    std::shared_ptr<Session> SessionManager::createTempSession() {
        return std::make_shared<Session>(support::key::generateUUID(), _cblManager);
    }

    std::shared_ptr<Session> SessionManager::getSession(const std::string &id) {
        std::lock_guard<std::mutex> lock(_mutex);
        auto it = _sessions.find(id);
        if (it == _sessions.end()) {
            throw support::error::RequestError("Session not found");
        }
        return it->second;
    }
}