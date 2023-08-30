#include "Dispatcher+Common.h"
#include <optional>
#include <unordered_set>

static string ErrorDesc(const string &docID, const string &collection, const string &reason) {
    return concat("Document '", docID, "' in '", collection, "' ", reason);
}

struct VerifyResult {
    bool ok;

    optional<string> description;

    optional<json> expectedValue;

    optional<json> actualValue;

    optional<json> actualDocument;

    json toJSON() {
        json result;
        result["result"] = ok;
        if (description) {
            result["description"] = description.value();
        }
        if (actualDocument) {
            result["document"] = actualDocument.value();
        }
        if (actualValue) {
            result["actual"] = actualValue.value();
        }
        if (expectedValue) {
            result["expected"] = expectedValue.value();
        }
        return result;
    }
};

bool
verifyProperties(const string &docID, const string &colName, FLDict props, FLDict expectedProps, VerifyResult &result) {
    string errKeyPath;
    auto isEquals = ts_support::fleece::valueIsEquals((FLValue) props, (FLValue) expectedProps, errKeyPath);
    if (!isEquals) {
        result.ok = false;
        auto reason = concat("had unexpected properties at key '", errKeyPath, "'");
        result.description = ErrorDesc(docID, colName, reason);

        auto actual = ts_support::fleece::valueAtKeyPath(props, errKeyPath);
        auto expected = ts_support::fleece::valueAtKeyPath(expectedProps, errKeyPath);

        result.actualDocument = ts_support::fleece::toJSON((FLValue) props);
        if (actual) {
            result.actualValue = ts_support::fleece::toJSON(actual);
        }
        if (expected) {
            result.expectedValue = ts_support::fleece::toJSON(expected);
        }
    } else {
        result.ok = true;
    }
    return result.ok;
}

int Dispatcher::handlePOSTVerifyDocuments(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    VerifyResult verifyResult{true};

    auto dbName = GetValue<string>(body, "database");
    auto db = _cblManager->database(dbName);

    auto snapshotID = GetValue<string>(body, "snapshot");
    auto snapshot = _cblManager->snapshot(snapshotID);

    // Verify changes:
    unordered_set<string> verifiedSnapShotDocs;
    auto changes = GetValue<vector<json>>(body, "changes");
    for (auto &change: changes) {
        auto colName = GetValue<string>(change, "collection");
        auto docID = GetValue<string>(change, "documentID");

        auto typeValue = GetValue<string>(change, "type");
        auto type = UpdateDatabaseTypeEnum.value(typeValue);

        bool mustExistInSnapShot = type != UpdateDatabaseType::update;
        auto snapshotDoc = snapshot->document(colName, docID, mustExistInSnapShot);
        verifiedSnapShotDocs.insert(Snapshot::documentKey(colName, docID));

        auto curDoc = CBLManager::document(db, colName, docID);
        AUTO_RELEASE(curDoc);

        if (type == UpdateDatabaseType::update) {
            if (!curDoc) {
                verifyResult.ok = false;
                verifyResult.description = ErrorDesc(docID, colName, "was not found");
                break;
            }

            CBLDocument *expectedDoc = snapshotDoc ?
                                       CBLDocument_MutableCopy(snapshotDoc) :
                                       CBLDocument_CreateWithID(FLS(docID));
            AUTO_RELEASE(expectedDoc);

            auto expectedProps = CBLDocument_MutableProperties(expectedDoc);
            if (change.contains("updatedProperties")) {
                auto updateItems = GetValue<vector<unordered_map<string, json>>>(change, "updatedProperties");
                ts_support::fleece::updateProperties(expectedProps, updateItems);
            }

            if (change.contains("removedProperties")) {
                auto keyPaths = GetValue<vector<string>>(change, "removedProperties");
                ts_support::fleece::removeProperties(expectedProps, keyPaths);
            }

            auto props = CBLDocument_Properties(curDoc);
            if (!verifyProperties(docID, colName, props, expectedProps, verifyResult)) {
                break;
            }
        } else if (type == UpdateDatabaseType::del) {
            if (curDoc) {
                verifyResult.ok = false;
                verifyResult.description = ErrorDesc(docID, colName, "was not deleted");
                break;
            }
        } else if (type == UpdateDatabaseType::purge) {
            if (curDoc) {
                verifyResult.ok = false;
                verifyResult.description = ErrorDesc(docID, colName, "was not purged");
                break;
            }
        } else {
            throw RequestError(concat("Invalid update type : ", typeValue));
        }
    }

    // Verify unchanged docs:
    if (verifyResult.ok) {
        auto allSnapDocs = snapshot->allDocuments();
        for (auto snapDocPair: allSnapDocs) {
            auto docKey = snapDocPair.first;
            auto docKeyComps = Snapshot::documentKeyComponents(snapDocPair.first);
            auto colName = docKeyComps.first;
            auto docID = docKeyComps.second;

            auto snapDoc = snapDocPair.second;
            if (snapDoc) {
                if (verifiedSnapShotDocs.find(docKey) == verifiedSnapShotDocs.end()) {
                    auto curDoc = CBLManager::document(db, colName, docID);
                    if (!curDoc) {
                        verifyResult.ok = false;
                        verifyResult.description = ErrorDesc(docID, colName, "was not found");
                        break;
                    }
                    auto props = CBLDocument_Properties(curDoc);
                    auto expectedProps = CBLDocument_Properties(snapDoc);
                    if (!verifyProperties(docID, colName, props, expectedProps, verifyResult)) {
                        break;
                    }
                }
            } else {
                auto curDoc = CBLManager::document(db, colName, docID);
                if (curDoc) {
                    verifyResult.ok = false;
                    verifyResult.description = ErrorDesc(docID, colName, "should not exist");
                    break;
                }
            }
        }
    }

    return request.respondWithJSON(verifyResult.toJSON());
}