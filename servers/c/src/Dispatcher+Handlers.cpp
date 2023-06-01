#include "Dispatcher.h"
#include "CollectionSpec.h"
#include "Common.h"
#include "Request.h"
#include "support/FleeceSupport.h"
#include "TestServer.h"

using namespace std;
using namespace nlohmann;

using ReplicatorParams = CBLManager::ReplicatorParams;
using ReplicationAuthenticator = CBLManager::ReplicationAuthenticator;
using ReplicationCollection = CBLManager::ReplicationCollection;

int Dispatcher::handleGETRoot(Request &request) { // NOLINT(readability-convert-member-functions-to-static)
    json result;
    result["version"] = TestServer::VERSION;
    result["apiVersion"] = TestServer::API_VERSION;
    result["cbl"] = TestServer::CBL_PLATFORM_NAME;
    return request.respondWithJSON(result);
}

int Dispatcher::handlePOSTReset(Request &request) {
    _cblManager->reset();
    json body = request.jsonBody();
    if (body.contains("datasets")) {
        json dataset = body["datasets"];
        for (auto &[key, val]: dataset.items()) {
            auto dbNames = val.get<vector<string>>();
            for (auto &name: dbNames) {
                _cblManager->loadDataset(key, name);
            }
        }
    }
    return request.respondWithOK();
}

int Dispatcher::handlePOSTGetAllDocumentIDs(Request &request) {
    json body = request.jsonBody();
    auto dbName = body["database"].get<string>();
    auto colNames = body["collections"].get<vector<string>>();

    auto db = _cblManager->database(dbName);

    json result = json::object();
    for (auto &colName: colNames) {
        auto col = _cblManager->collection(db, colName, false);
        AUTO_RELEASE(col);

        if (col) {
            CBLError error{};
            string str = "SELECT meta().id FROM " + colName;
            CBLQuery *query = CBLDatabase_CreateQuery(db, kCBLN1QLLanguage, FLS(str), nullptr, &error);
            checkError(error);
            AUTO_RELEASE(query);

            CBLResultSet *rs = CBLQuery_Execute(query, &error);
            checkError(error);
            AUTO_RELEASE(rs);

            vector<string> ids;
            while (CBLResultSet_Next(rs)) {
                FLString idVal = FLValue_AsString(CBLResultSet_ValueAtIndex(rs, 0));
                auto id = STR(idVal);
                ids.push_back(id);
            }
            result[colName] = ids;
        }
    }
    return request.respondWithJSON(result);
}

static void updateProperties(json &delta, FLMutableDict properties) { // NOLINT(misc-no-recursion)
    if (delta.type() != json::value_t::object) {
        throw domain_error("Applied delta is not dictionary");
    }

    for (const auto &[deltaKey, deltaValue]: delta.items()) {
        auto key = FLS(deltaKey);
        if (deltaValue.type() == json::value_t::object) {
            auto dict = FLMutableDict_GetMutableDict(properties, key);
            if (!dict) {
                dict = FLMutableDict_New();
                FLMutableDict_SetDict(properties, key, dict);
                FLMutableDict_Release(dict);
            }
            updateProperties(deltaValue, dict);
        } else {
            auto slot = FLMutableDict_Set(properties, key);
            ts_support::fleece::setSlotValue(slot, deltaValue);
        }
    }
}

static void removeProperties(json &removedProps, FLMutableDict properties) { // NOLINT(misc-no-recursion)
    if (removedProps.type() != json::value_t::object) {
        throw domain_error("Removed properties is not dictionary");
    }

    for (const auto &[deletedKey, deletedValue]: removedProps.items()) {
        auto key = FLS(deletedKey);
        if (deletedValue.type() == json::value_t::object) {
            auto dict = FLMutableDict_GetMutableDict(properties, key);
            if (!dict) {
                dict = FLMutableDict_New();
                FLMutableDict_SetDict(properties, key, dict);
                FLMutableDict_Release(dict);
            }
            removeProperties(deletedValue, dict);
        } else if (deletedValue.type() == json::value_t::null) {
            FLMutableDict_Remove(properties, key);
        } else {
            throw domain_error("Invalid removed property value");
        }
    }
}

int Dispatcher::handlePOSTUpdateDatabase(Request &request) {
    static constexpr const char *kUpdateDatabaseTypeUpdate = "UPDATE";
    static constexpr const char *kUpdateDatabaseTypeDelete = "DELETE";
    static constexpr const char *kUpdateDatabaseTypePurge = "PURGE";

    json body = request.jsonBody();
    auto dbName = body["database"].get<string>();
    auto db = _cblManager->database(dbName);
    
    {
        CBLError error{};

        bool commit = false;
        CBLDatabase_BeginTransaction(db, &error);
        checkError(error);
        DEFER { CBLDatabase_EndTransaction(db, commit, &error); };

        for (auto &update: body["updates"]) {
            auto colName = update["collection"].get<string>();
            auto spec = CollectionSpec(colName);
            auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
            checkError(error);
            AUTO_RELEASE(col);

            auto docID = update["documentID"].get<string>();
            CBLDocument *doc = CBLCollection_GetMutableDocument(col, FLS(docID), &error);
            checkError(error);
            AUTO_RELEASE(doc);

            auto type = update["type"].get<string>();
            if (type == kUpdateDatabaseTypeUpdate) {
                if (!doc) {
                    doc = CBLDocument_CreateWithID(FLS(docID));
                }
                auto props = FLDict_AsMutable(CBLDocument_Properties(doc));

                if (update.contains("updatedProperties")) {
                    json updatedProps = update["updatedProperties"];
                    updateProperties(updatedProps, props);
                }

                if (update.contains("removedProperties")) {
                    json removedProps = update["removedProperties"];
                    removeProperties(removedProps, props);
                }

                CBLCollection_SaveDocument(col, doc, &error);
                checkError(error);
            } else if (type == kUpdateDatabaseTypeDelete) {
                if (doc) {
                    CBLCollection_DeleteDocument(col, doc, &error);
                    checkError(error);
                }
            } else if (type == kUpdateDatabaseTypePurge) {
                if (doc) {
                    CBLCollection_PurgeDocument(col, doc, &error);
                    checkError(error);
                }
            }
        }
        commit = true;
    }
    return request.respondWithOK();
}

int Dispatcher::handlePOSTStartReplicator(Request &request) {
    json body = request.jsonBody();

    ReplicatorParams params;
    json config = body["config"];
    params.endpoint = config["endpoint"].get<string>();
    params.database = config["database"].get<string>();

    if (config.contains("replicatorType")) {
        auto replicatorType = config["replicatorType"].get<string>();
        if (replicatorType == "push") {
            params.replicatorType = kCBLReplicatorTypePush;
        } else if (replicatorType == "pull") {
            params.replicatorType = kCBLReplicatorTypePull;
        } else {
            params.replicatorType = kCBLReplicatorTypePushAndPull;
        }
    }

    if (config.contains("continuous")) {
        params.continuous = config["continuous"].get<bool>();
    }

    if (config.contains("authenticator")) {
        json authVal = config["authenticator"];
        if (authVal["type"].get<string>() == "BASIC") {
            ReplicationAuthenticator auth;
            auth.username = authVal["username"].get<string>();
            auth.password = authVal["password"].get<string>();
            params.authenticator = auth;
        }
    }

    vector<ReplicationCollection> collections;
    for (auto &colVal: config["collections"]) {
        ReplicationCollection col;
        col.collection = colVal["collection"].get<string>();
        if (colVal.contains("channels")) {
            col.channels = colVal["channels"].get<vector<string>>();
        }
        if (colVal.contains("documentIDs")) {
            col.documentIDs = colVal["documentIDs"].get<vector<string>>();
        }
        collections.push_back(col);
    }
    params.collections = collections;

    bool reset = false;
    if (body.contains("reset")) {
        reset = body["reset"].get<bool>();
    }

    string id = _cblManager->startReplicator(params, reset);

    json result;
    result["id"] = id;
    return request.respondWithJSON(result);
}

static const string kStatuses[5] = {"STOPPED", "OFFLINE", "CONNECTING", "IDLE", "BUSY"};

int Dispatcher::handlePOSTGetReplicatorStatus(Request &request) {
    json body = request.jsonBody();

    auto id = body["id"].get<string>();
    auto repl = _cblManager->replicator(id);
    if (!repl) {
        throw std::runtime_error("replicator not found");
    }

    json result;
    auto status = CBLReplicator_Status(repl);
    result["activity"] = kStatuses[(int) status.activity];

    json progress;
    progress["complete"] = status.progress.complete;
    progress["documentCount"] = status.progress.documentCount;
    result["progress"] = progress;

    if (status.error.code > 0) {
        json error;
        error["domain"] = (int) status.error.domain;
        error["code"] = status.error.code;

        FLSliceResult message = CBLError_Message(&status.error);
        if (message.size > 0) {
            error["message"] = STR(message);
        }
        FLSliceResult_Release(message);
    }

    return request.respondWithJSON(result);
}

// Handler Functions For Testing

int Dispatcher::handlePOSTGetDocument(Request &request) {
    json body = request.jsonBody();
    auto dbName = body["database"].get<string>();
    auto colName = body["collection"].get<string>();
    auto docID = body["documentID"].get<string>();

    auto db = _cblManager->database(dbName);
    auto col = _cblManager->collection(db, colName);

    CBLError error{};
    auto doc = CBLCollection_GetDocument(col, FLS(docID), &error);
    checkError(error);
    AUTO_RELEASE(doc);

    if (doc) {
        auto props = CBLDocument_Properties(doc);
        auto jsonSlice = FLValue_ToJSON((FLValue) props);
        DEFER { FLSliceResult_Release(jsonSlice); };

        auto json = nlohmann::json::parse(STR(jsonSlice));
        return request.respondWithJSON(json);
    } else {
        return request.respondWithServerError("Document Not Found");
    }
}
