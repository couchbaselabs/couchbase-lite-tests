#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTStopListener(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);
    auto id = GetValue<string>(body, "id");
    session->cblManager()->stopListener(id);
    return request.respondWithOK();
}
