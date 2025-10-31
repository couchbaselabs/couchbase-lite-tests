#include "SessionManager.h"

#include "CBLManager.h"
#include "Log.h"
#include "TestServer.h"

#include <filesystem>

namespace fs = std::filesystem;

using namespace ts::log;

namespace ts {
    std::string SessionManager::sessionsRootDirectory() const {
        return (fs::path(_testServer->context().filesDir) / "sessions").string();
    }

    void SessionManager::init() {
        auto sessionsRootDir = sessionsRootDirectory();
        if (fs::exists(sessionsRootDir)) {
            fs::remove_all(sessionsRootDir);
        }
        fs::create_directories(sessionsRootDir);
    }

    std::string SessionManager::createSessionDirectory(const std::string &id) {
        auto sessionDir = fs::path(sessionsRootDirectory()) / id;
        if (!fs::create_directories(sessionDir)) {
            throw std::runtime_error("Failed to create session directory '" + sessionDir.string() + "'");
        }
        Log::log(LogLevel::info, "Session directory created at '%s'", sessionDir.string().c_str());
        return sessionDir.string();
    }

    std::shared_ptr<Session> SessionManager::createSession(const std::string &id,
                                                           const std::string &datasetVersion) {
        std::lock_guard<std::mutex> lock(_mutex);
        if (_sessions.find(id) != _sessions.end()) {
            throw support::error::RequestError("Session with ID '" + id + "' already exists");
        }

        Log::log(LogLevel::info, "Creating session with ID '%s' and dataset version '%s'",
                 id.c_str(), datasetVersion.c_str());

        // Only have one session at least for now
        _sessions.clear();

        // Create CBLManager per session:
        auto context = _testServer->context();
        auto sessionDir = createSessionDirectory(id);
        auto cblManager = std::make_unique<cbl::CBLManager>(
            sessionDir, context.assetsDir, datasetVersion);

        // Create session:
        auto session = std::make_shared<Session>(id, std::move(cblManager));
        _sessions.emplace(id, session);
        Log::log(LogLevel::info, "Session '%s' created successfully", id.c_str());
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