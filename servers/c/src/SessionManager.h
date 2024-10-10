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
    class Session {
    public:
        Session(std::string id, std::shared_ptr<ts::cbl::CBLManager> cblManager)
            : _id(std::move(id)), _cblManager(std::move(cblManager)) {}

        [[nodiscard]]
        const std::string &id() const { return _id; }

        [[nodiscard]]
        std::shared_ptr<ts::cbl::CBLManager> cblManager() const { return _cblManager; }

    private:
        std::string _id;
        std::shared_ptr<ts::cbl::CBLManager> _cblManager;
    };

    class SessionManager {
    public:
        explicit SessionManager(std::shared_ptr<ts::cbl::CBLManager> cblManager)
            : _cblManager(std::move(cblManager)) {}

        std::shared_ptr<Session> createSession(const std::string &id) {
            std::lock_guard<std::mutex> lock(_mutex);
            if (_sessions.find(id) != _sessions.end()) {
                throw support::error::RequestError("Session with given ID already exists");
            }

            auto session = std::make_shared<Session>(id, _cblManager);
            _sessions.emplace(id, session);
            return session;
        }

        std::shared_ptr<Session> createTempSession() {
            return std::make_shared<Session>(support::key::generateUUID(), _cblManager);
        }

        std::shared_ptr<Session> getSession(const std::string &id) {
            std::lock_guard<std::mutex> lock(_mutex);
            auto it = _sessions.find(id);
            if (it == _sessions.end()) {
                throw support::error::RequestError("Session not found");
            }
            return it->second;
        }

    private:
        mutable std::mutex _mutex;
        std::unordered_map<std::string, std::shared_ptr<Session>> _sessions;
        std::shared_ptr<ts::cbl::CBLManager> _cblManager;
    };
}


