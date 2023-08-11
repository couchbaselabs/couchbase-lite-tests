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
            auto type = GetValue<string>(update, "type");
            if (EnumEquals(type, kUpdateDatabaseTypeUpdate)) {
                CBLDocument *doc = CBLCollection_GetMutableDocument(col, FLS(docID), &error);
                CheckError(error);
                if (!doc) {
                    doc = CBLDocument_CreateWithID(FLS(docID));
                }
                AUTO_RELEASE(doc);

                auto props = CBLDocument_MutableProperties(doc);
                if (update.contains("updatedProperties")) {
                    auto updateItems = GetValue<vector<unordered_map<string, json>>>(update, "updatedProperties");
                    ts_support::fleece::updateProperties(props, updateItems);
                }

                if (update.contains("removedProperties")) {
                    auto keyPaths = GetValue<vector<string>>(update, "removedProperties");
                    ts_support::fleece::removeProperties(props, keyPaths);
                }

                CBLCollection_SaveDocument(col, doc, &error);
                CheckError(error);
            } else if (EnumEquals(type, kUpdateDatabaseTypeDelete)) {
                CBLDocument *doc = CBLCollection_GetMutableDocument(col, FLS(docID), &error);
                CheckError(error);
                if (doc) {
                    CBLCollection_DeleteDocument(col, doc, &error);
                    CheckError(error);
                }
            } else if (EnumEquals(type, kUpdateDatabaseTypePurge)) {
                CBLCollection_PurgeDocumentByID(col, FLS(docID), &error);
                CheckError(error);
            }
        }
        commit = true;
    }
    return request.respondWithOK();
}