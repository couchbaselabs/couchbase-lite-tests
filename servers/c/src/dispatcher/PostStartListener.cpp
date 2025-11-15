#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTStartListener(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    auto database = GetValue<string>(body, "database");

    auto collections = GetValue<vector<string>>(body, "collections");
    if (collections.empty()) {
        throw RequestError("No collections specified");
    }

    auto port = GetValue<int>(body, "port", 0);
    auto disableTLS = GetValue<bool>(body, "disableTLS", false);

    string id = session->cblManager()->startListener(database, collections, port, disableTLS);

    json result;
    result["id"] = id;
    return request.respondWithJSON(result);
}
