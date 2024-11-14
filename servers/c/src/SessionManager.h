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
        Session(std::string id, cbl::CBLManager *cblManager)
            : _id(std::move(id)), _cblManager(cblManager) {}

        [[nodiscard]]
        const std::string &id() const { return _id; }

        [[nodiscard]]
        ts::cbl::CBLManager *cblManager() const { return _cblManager; }

    private:
        std::string _id;
        cbl::CBLManager *_cblManager;
    };

    class SessionManager {
    public:
        explicit SessionManager(cbl::CBLManager *cblManager) : _cblManager(cblManager) {}

        std::shared_ptr<Session> createSession(const std::string &id);

        std::shared_ptr<Session> createTempSession();

        std::shared_ptr<Session> getSession(const std::string &id);

    private:
        mutable std::mutex _mutex;
        cbl::CBLManager *_cblManager;
        std::unordered_map<std::string, std::shared_ptr<Session>> _sessions;
    };
}