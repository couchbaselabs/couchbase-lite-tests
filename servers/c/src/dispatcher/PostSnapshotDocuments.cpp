#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTSnapshotDocuments(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto documents = GetValue<vector<json>>(body, "documents");

    auto cblManager = session->cblManager();
    auto db = cblManager->database(dbName);
    auto snapshot = cblManager->createSnapshot();
    try {
        for (auto &docInfo: documents) {
            auto collectionName = GetValue<string>(docInfo, "collection");
            auto docID = GetValue<string>(docInfo, "id");
            auto doc = CBLManager::document(db, collectionName, docID);
            AUTO_RELEASE(doc);
            snapshot->putDocument(collectionName, docID, doc);
        }
    } catch (const std::exception &e) {
        cblManager->deleteSnapshot(snapshot->id());
        throw e;
    }

    json result;
    result["id"] = snapshot->id();
    return request.respondWithJSON(result);
}