#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTLog(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);
    auto message = GetValue<string>(body, "message");
    Log::log(LogLevel::info, "%s", message.c_str());
    return request.respondWithOK();
}
