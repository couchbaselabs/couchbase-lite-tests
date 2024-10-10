#include "Dispatcher+Common.h"

// Handler Functions For Internal Testing

// TODO: Enable this when 4.0 binary is ready
//extern "C" {
//FLString CBLDocument_RevisionHistory(const CBLDocument *doc);
//}

int Dispatcher::handlePOSTGetDocument(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto docInfo = GetValue<json>(body, "document");
    auto colName = GetValue<string>(docInfo, "collection");
    auto docID = GetValue<string>(docInfo, "id");

    auto cblManager = session->cblManager();
    auto db = cblManager->database(dbName);
    auto col = cblManager->collection(db, colName);

    CBLError error{};
    auto doc = CBLCollection_GetDocument(col, FLS(docID), &error);
    checkCBLError(error);
    checkNotNull(doc, str::concat("Document '", colName, ".", docID, "' not found"));
    AUTO_RELEASE(doc);

    auto props = CBLDocument_Properties(doc);
    auto json = ts_support::fleece::toJSON((FLValue) props);
    json["_id"] = docID;

    // TODO: Use CBLDocument_RevisionHistory(doc) instead when 4.0 binary is ready.
    json["_revs"] = STR(CBLDocument_RevisionID(doc));
    return request.respondWithJSON(json);
}
