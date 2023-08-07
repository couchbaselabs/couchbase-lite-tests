#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTGetAllDocuments(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto colNames = GetValue<vector<string>>(body, "collections");

    auto db = _cblManager->database(dbName);
    json result = json::object();
    for (auto &colName: colNames) {
        auto col = CBLManager::collection(db, colName, false);
        AUTO_RELEASE(col);

        if (col) {
            CBLError error{};
            string str = "SELECT meta().id, meta().revisionID FROM " + colName;
            CBLQuery *query = CBLDatabase_CreateQuery(db, kCBLN1QLLanguage, FLS(str), nullptr, &error);
            CheckError(error);
            AUTO_RELEASE(query);

            CBLResultSet *rs = CBLQuery_Execute(query, &error);
            CheckError(error);
            AUTO_RELEASE(rs);

            vector<json> docs;
            while (CBLResultSet_Next(rs)) {
                json doc;
                FLString idVal = FLValue_AsString(CBLResultSet_ValueAtIndex(rs, 0));
                doc["id"] = STR(idVal);
                FLString revVal = FLValue_AsString(CBLResultSet_ValueAtIndex(rs, 1));
                doc["rev"] = STR(revVal);
                docs.push_back(doc);
            }
            result[colName] = docs;
        }
    }
    return request.respondWithJSON(result);
}