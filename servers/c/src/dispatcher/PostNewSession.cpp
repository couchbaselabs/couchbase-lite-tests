#include "Dispatcher+Common.h"
#include "RemoteLogger.h"
#include <map>
#include <memory>

using namespace std;

int Dispatcher::handlePOSTNewSession(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    // Session Parameters:
    auto id = GetValue<string>(body, "id");
    auto datasetVersion = GetValue<string>(body, "dataset_version");

    // Create Session:
    auto sessionManager = request.dispatcher()->sessionManager();
    auto newSession = sessionManager->createSession(id, datasetVersion);
    Log::logToConsole(LogLevel::info, "Start new session with id '%s' and dataset version '%s'",
                      id.c_str(), datasetVersion.c_str());

    // Logging:
    auto logging = GetOptValue<json>(body, "logging");
    if (logging) {
        auto url = GetValue<string>(logging.value(), "url");
        auto tag = GetValue<string>(logging.value(), "tag");
        Log::logToConsole(LogLevel::info, "Use remote logger '%s' with log-id '%s' and tag '%s'",
                          url.c_str(), newSession->id().c_str(), tag.c_str());

        map<string, string> headers;
        headers["CBL-Log-ID"] = newSession->id();
        headers["CBL-Log-Tag"] = tag;
        auto remoteLogger = make_shared<RemoteLogger>(url, headers);
        remoteLogger->connect(10s);
        Log::useCustomLogger(remoteLogger);
    } else {
        Log::useDefaultLogger();
    }

    return request.respondWithJSON({});
}
