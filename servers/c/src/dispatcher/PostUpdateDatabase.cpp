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
        checkCBLError(error);
        DEFER { CBLDatabase_EndTransaction(db, commit, &error); };

        vector<CBLBlob *> retainedBlobs;
        DEFER {
                  for (auto blob: retainedBlobs) {
                      CBLBlob_Release(blob);
                  }
              };

        auto updates = GetValue<vector<json>>(body, "updates");
        for (auto &update: updates) {
            auto colName = GetValue<string>(update, "collection");
            auto spec = CollectionSpec(colName);
            auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
            checkCBLError(error);
            if (!col) {
                throw RequestError("Collection '" + spec.fullName() + "' Not Found");
            }
            AUTO_RELEASE(col);

            auto docID = GetValue<string>(update, "documentID");
            auto typeValue = GetValue<string>(update, "type");
            auto type = UpdateDatabaseTypeEnum.value(typeValue);

            if (type == UpdateDatabaseType::update) {
                CBLDocument *doc = CBLCollection_GetMutableDocument(col, FLS(docID), &error);
                checkCBLError(error);
                if (!doc) {
                    doc = CBLDocument_CreateWithID(FLS(docID));
                }
                AUTO_RELEASE(doc);

                auto props = CBLDocument_MutableProperties(doc);
                ts_support::fleece::applyDeltaUpdates(props, update, [&](const string &name) -> CBLBlob * {
                    auto blob = _cblManager->blob(name, db);
                    retainedBlobs.push_back(blob);
                    return blob;
                });

                CBLCollection_SaveDocument(col, doc, &error);
                checkCBLError(error);
            } else if (type == UpdateDatabaseType::del) {
                CBLDocument *doc = CBLCollection_GetMutableDocument(col, FLS(docID), &error);
                checkCBLError(error);
                if (doc) {
                    CBLCollection_DeleteDocument(col, doc, &error);
                    checkCBLError(error);
                }
            } else if (type == UpdateDatabaseType::purge) {
                CBLCollection_PurgeDocumentByID(col, FLS(docID), &error);
                checkCBLError(error);
            } else {
                throw RequestError(concat("Invalid update type : ", typeValue));
            }
        }
        commit = true;
    }
    return request.respondWithOK();
}
