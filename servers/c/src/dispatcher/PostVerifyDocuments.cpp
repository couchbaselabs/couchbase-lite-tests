#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTVerifyDocuments(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    bool verifiedResult = true;
    string description;

    json expected = nullptr;
    json actual = nullptr;

    auto dbName = GetValue<string>(body, "database");
    auto db = _cblManager->database(dbName);

    auto snapshotID = GetValue<string>(body, "snapshot");
    auto snapshot = _cblManager->snapshot(snapshotID);

    auto changes = GetValue<vector<json>>(body, "changes");
    for (auto &change: changes) {
        auto colName = GetValue<string>(change, "collection");
        auto docID = GetValue<string>(change, "documentID");
        auto snapshotDoc = snapshot->document(colName, docID);
        auto curDoc = CBLManager::document(db, colName, docID);
        AUTO_RELEASE(curDoc);

        auto type = GetValue<string>(change, "type");
        if (EnumEquals(type, kUpdateDatabaseTypeUpdate)) {
            if (!curDoc) {
                verifiedResult = false;
                description = Concat("Document '", colName, ".", docID, "' not exist");
                break;
            }

            CBLDocument *expectedDoc = snapshotDoc ?
                                       CBLDocument_MutableCopy(snapshotDoc) :
                                       CBLDocument_CreateWithID(FLS(docID));
            AUTO_RELEASE(expectedDoc);
            auto expectedProps = CBLDocument_MutableProperties(expectedDoc);
            if (change.contains("updatedProperties")) {
                auto updatedProps = GetValue<vector<unordered_map<string, json>>>(change, "updatedProperties");
                for (auto &keyPaths: updatedProps) {
                    for (auto &keyPath: keyPaths) {
                        try {
                            ts_support::fleece::updateProperties(expectedProps, FLS(keyPath.first), keyPath.second);
                        } catch (const std::exception &e) {
                            throw RequestError(e.what());
                        }
                    }
                }
            }

            if (change.contains("removedProperties")) {
                auto keyPaths = GetValue<vector<string>>(change, "removedProperties");
                for (auto &keyPath: keyPaths) {
                    try {
                        ts_support::fleece::removeProperties(expectedProps, FLS(keyPath));
                    } catch (const std::exception &e) {
                        throw RequestError(e.what());
                    }
                }
            }

            auto props = CBLDocument_Properties(curDoc);
            FLDict delta = ts_support::fleece::compareDicts(props, expectedProps);
            DEFER { FLDict_Release(delta); };
            if (FLDict_Count(delta) > 0) {
                verifiedResult = false;
                auto deltaJSON = FLValue_ToJSON5((FLValue) delta);
                DEFER { FLSliceResult_Release(deltaJSON); };
                description = Concat("Document '", colName, ".", docID, "' has unexpected changes; delta : ",
                                     STR(deltaJSON));
                actual = ts_support::fleece::toJSON((FLValue) props);
                expected = ts_support::fleece::toJSON((FLValue) expectedProps);
                break;
            }
        } else if (EnumEquals(type, kUpdateDatabaseTypeDelete) ||
                   EnumEquals(type, kUpdateDatabaseTypePurge)) {
            if (curDoc) {
                verifiedResult = false;
                description = Concat("Document '", colName, ".", docID, "' not deleted or purged");
                break;
            }
        }
    }

    json result;
    result["result"] = verifiedResult;
    if (!description.empty()) {
        result["description"] = description;
    }
    if (actual.type() == json::value_t::object) {
        result["actual"] = actual;
    }
    if (expected.type() == json::value_t::object) {
        result["expected"] = expected;
    }
    return request.respondWithJSON(result);
}