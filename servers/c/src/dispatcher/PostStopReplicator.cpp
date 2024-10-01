#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTStopReplicator(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);
    auto id = GetValue<string>(body, "id");
    _cblManager->stopReplicator(id);
    return request.respondWithOK();
}