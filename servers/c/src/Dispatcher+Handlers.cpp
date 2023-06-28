#include "Dispatcher.h"
#include "CollectionSpec.h"
#include "Request.h"
#include "support/Defer.h"
#include "support/Define.h"
#include "support/Device.h"
#include "support/Fleece.h"
#include "support/JSON.h"
#include "TestServer.h"

using namespace std;
using namespace nlohmann;

using ReplicatorParams = CBLManager::ReplicatorParams;
using ReplicationAuthenticator = CBLManager::ReplicationAuthenticator;
using ReplicationCollection = CBLManager::ReplicationCollection;

static inline void CheckBody(const json &body) {
    if (!body.is_object()) {
        throw domain_error("Request body is not json object");
    }
}

int Dispatcher::handleGETRoot(Request &request) { // NOLINT(readability-convert-member-functions-to-static)
    json result;
    result["version"] = TestServer::VERSION;
    result["apiVersion"] = TestServer::API_VERSION;
    result["cbl"] = TestServer::CBL_PLATFORM_NAME;

    json device;
    string model = ts_support::device::deviceModel();
    if (!model.empty()) {
        device["model"] = model;
    }
    string osName = ts_support::device::osName();
    if (!osName.empty()) {
        device["systemName"] = osName;
    }
    string osVersion = ts_support::device::osVersion();
    if (!osVersion.empty()) {
        device["systemVersion"] = osVersion;
    }
    string apiVersion = ts_support::device::apiVersion();
    if (!apiVersion.empty()) {
        device["systemApiVersion"] = apiVersion;
    }
    result["device"] = device;

    return request.respondWithJSON(result);
}

int Dispatcher::handlePOSTReset(Request &request) {
    _cblManager->reset();

    json body = request.jsonBody();
    CheckBody(body);
    if (body.contains("datasets")) {
        auto datasets = GetValue<unordered_map<string, vector<string>>>(body, "datasets");
        for (auto &dataset: datasets) {
            auto datasetName = dataset.first;
            auto dbNames = dataset.second;
            if (dbNames.empty()) {
                throw domain_error("dataset '" + datasetName + "' has no database names");
            }
            for (auto &dbName: dbNames) {
                _cblManager->loadDataset(datasetName, dbName);
            }
        }
    }
    return request.respondWithOK();
}

int Dispatcher::handlePOSTGetAllDocumentIDs(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    auto dbName = GetValue<string>(body, "database");
    auto colNames = GetValue<vector<string>>(body, "collections");

    auto db = _cblManager->database(dbName);
    json result = json::object();
    for (auto &colName: colNames) {
        auto col = _cblManager->collection(db, colName, false);
        AUTO_RELEASE(col);

        if (col) {
            CBLError error{};
            string str = "SELECT meta().id FROM " + colName;
            CBLQuery *query = CBLDatabase_CreateQuery(db, kCBLN1QLLanguage, FLS(str), nullptr, &error);
            CheckError(error);
            AUTO_RELEASE(query);

            CBLResultSet *rs = CBLQuery_Execute(query, &error);
            CheckError(error);
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
            AUTO_RELEASE(col);

            auto docID = GetValue<string>(update, "documentID");
            CBLDocument *doc = CBLCollection_GetMutableDocument(col, FLS(docID), &error);
            CheckError(error);
            AUTO_RELEASE(doc);

            auto type = GetValue<string>(update, "type");
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
                CheckError(error);
            } else if (type == kUpdateDatabaseTypeDelete) {
                if (doc) {
                    CBLCollection_DeleteDocument(col, doc, &error);
                    CheckError(error);
                }
            } else if (type == kUpdateDatabaseTypePurge) {
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

int Dispatcher::handlePOSTStartReplicator(Request &request) {
    static constexpr const char *kReplicatorTypePush = "push";
    static constexpr const char *kReplicatorTypePull = "pull";
    static constexpr const char *kReplicatorTypePushAndPull = "pushAndPull";
    static constexpr const char *kAuthTypeBasic = "BASIC";

    json body = request.jsonBody();
    CheckBody(body);

    ReplicatorParams params;
    json config = GetValue<json>(body, "config");
    CheckIsObject(config, "config");

    params.endpoint = GetValue<string>(config, "endpoint");
    params.database = GetValue<string>(config, "database");

    if (config.contains("replicatorType")) {
        auto replicatorType = GetValue<string>(config, "replicatorType");
        if (replicatorType == kReplicatorTypePush) {
            params.replicatorType = kCBLReplicatorTypePush;
        } else if (replicatorType == kReplicatorTypePull) {
            params.replicatorType = kCBLReplicatorTypePull;
        } else if (replicatorType == kReplicatorTypePushAndPull) {
            params.replicatorType = kCBLReplicatorTypePushAndPull;
        } else {
            throw domain_error("Invalid replicator type");
        }
    }

    if (config.contains("continuous")) {
        params.continuous = GetValue<bool>(config, "continuous");
    }

    if (config.contains("authenticator")) {
        json authObject = config["authenticator"];
        CheckIsObject(authObject, "authenticator");
        if (GetValue<string>(authObject, "type") == kAuthTypeBasic) {
            ReplicationAuthenticator auth;
            auth.username = GetValue<string>(authObject, "username");
            auth.password = GetValue<string>(authObject, "password");
            params.authenticator = auth;
        }
    }

    vector<ReplicationCollection> collections;
    for (auto &colObject: GetValue<vector<json>>(config, "collections")) {
        ReplicationCollection col;
        col.collection = GetValue<string>(colObject, "collection");
        if (colObject.contains("channels")) {
            col.channels = GetValue<vector<string>>(colObject, "channels");
        }
        if (colObject.contains("documentIDs")) {
            col.documentIDs = GetValue<vector<string>>(colObject, "documentIDs");
        }
        if (colObject.contains("pushFilter")) {
            auto filterObject = GetValue<json>(colObject, "pushFilter");
            ReplicationFilterSpec filterSpec = {};
            filterSpec.name = GetValue<string>(filterObject, "name");
            filterSpec.params = filterObject.contains("params") ?
                                GetValue<json>(filterObject, "params") : json::object();
            col.pushFilter = filterSpec;
        }
        if (colObject.contains("pullFilter")) {
            auto filterObject = GetValue<json>(colObject, "pullFilter");
            ReplicationFilterSpec filterSpec = {};
            filterSpec.name = GetValue<string>(filterObject, "name");
            filterSpec.params = filterObject.contains("params") ?
                                GetValue<json>(filterObject, "params") : json::object();
            col.pullFilter = filterSpec;
        }
        collections.push_back(col);
    }
    params.collections = collections;

    bool reset = false;
    if (body.contains("reset")) {
        reset = GetValue<bool>(body, "reset");
    }

    string id = _cblManager->startReplicator(params, reset);

    json result;
    result["id"] = id;
    return request.respondWithJSON(result);
}

static const string kStatuses[5] = {"STOPPED", "OFFLINE", "CONNECTING", "IDLE", "BUSY"};

int Dispatcher::handlePOSTGetReplicatorStatus(Request &request) {
    json body = request.jsonBody();
    CheckBody(body);

    auto id = GetValue<string>(body, "id");
    auto repl = _cblManager->replicator(id);
    if (!repl) {
        throw std::domain_error("Replicator '" + id + "' not found");
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
        result["error"] = error;
    }

    return request.respondWithJSON(result);
}

// Handler Functions For Testing

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
    CheckError(error);
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
