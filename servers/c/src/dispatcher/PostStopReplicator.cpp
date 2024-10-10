#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTStopReplicator(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);
    auto id = GetValue<string>(body, "id");
    session->cblManager()->stopReplicator(id);
    return request.respondWithOK();
}