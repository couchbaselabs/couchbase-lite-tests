#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTReset(Request &request, Session *session) {
    auto cblManager = session->cblManager();
    cblManager->reset();

    json body = request.jsonBody();
    CheckBody(body);

    auto test = GetOptValue<string>(body, "test");
    if (test) {
        Log::log(LogLevel::info, ">>>>>>>>>> %s <<<<<<<<<<", test->c_str());
    }

    if (body.contains("databases")) {
        auto databases = GetValue<unordered_map<string, json>>(body, "databases");
        for (auto &db: databases) {
            auto dbName = db.first;
            if (dbName.empty()) {
                throw RequestError("database name cannot be empty.");
            }

            auto spec = db.second;
            if (spec.empty()) {
                cblManager->createDatabaseWithCollections(dbName, {});
            } else {
                if (spec.contains("collections") && spec.contains("dataset")) {
                    throw RequestError("Database cannot contain both collections and dataset.");
                }
                if (spec.contains("collections")) {
                    auto collections = GetValue<vector<string>>(spec, "collections");
                    cblManager->createDatabaseWithCollections(dbName, collections);
                } else if (spec.contains("dataset")) {
                    auto dataset = GetValue<string>(spec, "dataset");
                    cblManager->createDatabaseWithDataset(dbName, dataset);
                } else {
                    throw RequestError(
                        "Database must contain either collections, dataset, or empty.");
                }
            }
        }
    }
    return request.respondWithOK();
}