#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTRunQuery(Request &request, Session *session) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto queryStr = GetValue<string>(body, "query");

    auto db = session->cblManager()->database(dbName);

    CBLError error{};
    auto query = CBLDatabase_CreateQuery(db, kCBLN1QLLanguage, FLS(queryStr), nullptr, &error);
    checkCBLError(error);
    AUTO_RELEASE(query);

    auto rs = CBLQuery_Execute(query, &error);
    checkCBLError(error);
    AUTO_RELEASE(rs);

    json result = json::object();
    vector<json> rows;
    while (CBLResultSet_Next(rs)) {
        auto dict = CBLResultSet_ResultDict(rs);
        auto json = ts_support::fleece::toJSON((FLValue) dict);
        rows.push_back(json);
    }
    result["results"] = rows;
    return request.respondWithJSON(result);
}
