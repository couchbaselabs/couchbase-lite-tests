#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTNewSession(Request &request, Session *session) {
    return request.respondWithOK();
}