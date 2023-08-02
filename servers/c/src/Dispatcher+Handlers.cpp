#include "Dispatcher.h"
#include "CollectionSpec.h"
#include "Request.h"
#include "support/Defer.h"
#include "support/Define.h"
#include "support/Device.h"
#include "support/Exception.h"
#include "support/Fleece.h"
#include "support/JSON.h"
#include "TestServer.h"

using namespace std;
using namespace nlohmann;
using namespace ts_support::exception;

using ReplicatorParams = CBLManager::ReplicatorParams;
using ReplicationAuthenticator = CBLManager::ReplicationAuthenticator;
using ReplicationCollection = CBLManager::ReplicationCollection;

static inline void CheckBody(const json &body) {
    if (!body.is_object()) {
        throw RequestError("Request body is not json object");
    }
}

int Dispatcher::handleGETRoot(Request &request) { // NOLINT(readability-convert-member-functions-to-static)
    json result;
    result["version"] = CBLManager::version();
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
    result["additionalInfo"] = "Edition: " + CBLManager::edition() + ", Build: " + to_string(CBLManager::buildNumber());

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
                throw RequestError("dataset '" + datasetName + "' has no database names");
            }
            for (auto &dbName: dbNames) {
                _cblManager->loadDataset(datasetName, dbName);
            }
        }
    }
    return request.respondWithOK();
}

int Dispatcher::handlePOSTGetAllDocuments(Request &request) {
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

                auto props = CBLDocument_MutableProperties(doc);

                if (update.contains("updatedProperties")) {
                    auto updatedProps = GetValue<vector<unordered_map<string, json>>>(update, "updatedProperties");
                    for (auto &keyPaths: updatedProps) {
                        for (auto &keyPath: keyPaths) {
                            try {
                                ts_support::fleece::updateProperties(props, FLS(keyPath.first), keyPath.second);
                            } catch (const exception &e) {
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
                        } catch (const exception &e) {
                            throw RequestError(e.what());
                        }
                    }
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
            throw RequestError("Invalid replicator type");
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

    if (config.contains("enableDocumentListener")) {
        params.enableDocumemntListener = GetValue<bool>(config, "enableDocumentListener");
    }

    vector<ReplicationCollection> collections;
    for (auto &colObject: GetValue<vector<json>>(config, "collections")) {
        vector<string> names;
        if (colObject.contains("names")) {
            names = GetValue<vector<string>>(colObject, "names");
        } else {
            // TODO: Remove this when python client makes changes to use names
            auto name = GetValue<string>(colObject, "collection");
            names.push_back(name);
        }
        if (names.empty()) {
            throw RequestError("No collections specified");
        }

        for (auto &name: names) {
            ReplicationCollection col;
            col.collection = name;
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
    auto replStatus = _cblManager->status(id);
    if (!replStatus) {
        throw RequestError("Replicator '" + id + "' not found");
    }

    json result;
    auto status = replStatus->status;
    result["activity"] = kStatuses[(int) status.activity];

    json progress;
    progress["completed"] = status.progress.complete == 1.0;
    result["progress"] = progress;

    if (status.error.code > 0) {
        result["error"] = CBLException(status.error).json();
    }

    if (replStatus->replicatedDocs) {
        vector<json> docs;
        auto &batches = replStatus->replicatedDocs.value();
        for (auto &batch: batches) {
            for (auto &replDoc: batch) {
                json doc;
                doc["isPush"] = replDoc.isPush;
                doc["collection"] = replDoc.collection;
                doc["documentID"] = replDoc.documentID;
                if (replDoc.error.code > 0) {
                    doc["error"] = CBLException(replDoc.error).json();
                }
                if (replDoc.flags) {
                    vector<string> flags;
                    if (replDoc.flags & kCBLDocumentFlagsDeleted) { flags.emplace_back("DELETED"); }
                    if (replDoc.flags & kCBLDocumentFlagsAccessRemoved) { flags.emplace_back("ACCESSREMOVED"); }
                    if (!flags.empty()) { doc["flags"] = flags; }
                }
                docs.push_back(doc);
            }
        }
        result["docs"] = docs;
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
        throw RequestError("Document '" + docID + "' in collection '" + colName + "' of database '" + dbName +
                           "' not found");
    }
}
