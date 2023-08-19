#include "Dispatcher+Common.h"

// Handler Functions For Internal Testing

int Dispatcher::handlePOSTGetDocument(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto colName = GetValue<string>(body, "collection");
    auto docID = GetValue<string>(body, "documentID");

    auto db = _cblManager->database(dbName);
    auto col = _cblManager->collection(db, colName);

    CBLError error{};
    auto doc = CBLCollection_GetDocument(col, FLS(docID), &error);
    checkCBLError(error);
    AUTO_RELEASE(doc);

    if (doc) {
        auto props = CBLDocument_Properties(doc);
        auto jsonSlice = FLValue_ToJSON((FLValue) props);
        DEFER { FLSliceResult_Release(jsonSlice); };

        auto json = nlohmann::json::parse(STR(jsonSlice));
        return request.respondWithJSON(json);
    } else {
        throw RequestError(str::concat("Document '", colName, ".", docID, "' not found"));
    }
}
