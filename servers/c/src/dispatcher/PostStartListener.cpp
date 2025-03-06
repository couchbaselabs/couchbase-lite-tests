#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTStartListener(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    // TODO: Implement this

    json result;
    return request.respondWithJSON(result);
}
