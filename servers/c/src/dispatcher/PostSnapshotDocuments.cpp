#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTSnapshotDocuments(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto documents = GetValue<vector<json>>(body, "documents");

    auto db = _cblManager->database(dbName);
    auto snapshot = _cblManager->createSnapshot();
    try {
        for (auto &docInfo: documents) {
            auto collectionName = GetValue<string>(docInfo, "collection");
            auto docID = GetValue<string>(docInfo, "id");
            auto doc = CBLManager::document(db, collectionName, docID);
            AUTO_RELEASE(doc);
            snapshot->putDocument(collectionName, docID, doc);
        }
    } catch (const std::exception &e) {
        _cblManager->deleteSnapshot(snapshot->id());
        throw e;
    }

    json result;
    result["id"] = snapshot->id();
    return request.respondWithJSON(result);
}