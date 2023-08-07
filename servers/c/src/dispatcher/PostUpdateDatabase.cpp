#include "Dispatcher+Common.h"

int Dispatcher::handlePOSTUpdateDatabase(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto db = _cblManager->database(dbName);
    {
        CBLError error{};
        bool commit = false;
        CBLDatabase_BeginTransaction(db, &error);
        CheckError(error);
        DEFER { CBLDatabase_EndTransaction(db, commit, &error); };

        auto updates = GetValue<vector<json>>(body, "updates");
        for (auto &update: updates) {
            auto colName = GetValue<string>(update, "collection");
            auto spec = CollectionSpec(colName);
            auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
            CheckError(error);
            if (!col) {
                throw RequestError("Collection '" + spec.fullName() + "' Not Found");
            }
            AUTO_RELEASE(col);

            auto docID = GetValue<string>(update, "documentID");
            CBLDocument *doc = CBLCollection_GetMutableDocument(col, FLS(docID), &error);
            CheckError(error);
            AUTO_RELEASE(doc);

            auto type = GetValue<string>(update, "type");
            if (EnumEquals(type, kUpdateDatabaseTypeUpdate)) {
                if (!doc) {
                    doc = CBLDocument_CreateWithID(FLS(docID));
                }

                auto props = CBLDocument_MutableProperties(doc);

                if (update.contains("updatedProperties")) {
                    auto updatedProps = GetValue<vector<unordered_map<string, json>>>(update, "updatedProperties");
                    for (auto &keyPaths: updatedProps) {
                        for (auto &keyPath: keyPaths) {
                            try {
                                ts_support::fleece::updateProperties(props, FLS(keyPath.first), keyPath.second);
                            } catch (const std::exception &e) {
                                throw RequestError(e.what());
                            }
                        }
                    }
                }

                if (update.contains("removedProperties")) {
                    auto keyPaths = GetValue<vector<string>>(update, "removedProperties");
                    for (auto &keyPath: keyPaths) {
                        try {
                            ts_support::fleece::removeProperties(props, FLS(keyPath));
                        } catch (const std::exception &e) {
                            throw RequestError(e.what());
                        }
                    }
                }

                CBLCollection_SaveDocument(col, doc, &error);
                CheckError(error);
            } else if (EnumEquals(type, kUpdateDatabaseTypeDelete)) {
                if (doc) {
                    CBLCollection_DeleteDocument(col, doc, &error);
                    CheckError(error);
                }
            } else if (EnumEquals(type, kUpdateDatabaseTypePurge)) {
                if (doc) {
                    CBLCollection_PurgeDocument(col, doc, &error);
                    CheckError(error);
                }
            }
        }
        commit = true;
    }
    return request.respondWithOK();
}