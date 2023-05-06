#include "Dispatcher.h"
#include "CollectionSpec.h"
#include "Common.h"
#include "Request.h"

using namespace std;
using namespace nlohmann;

using ReplicatorParams = CBLManager::ReplicatorParams;
using ReplicationAuthenticator = CBLManager::ReplicationAuthenticator;
using ReplicationCollection = CBLManager::ReplicationCollection;

int Dispatcher::handleGETRoot(Request &request) {
    json result;
    result["version"] = "3.1.0";
    result["apiVersion"] = 1;
    result["cbl"] = "couchbase-lite-c";
    return request.respondWithJSON(result);
}

int Dispatcher::handlePOSTReset(Request &request) {
    _dbManager->reset();
    json body = request.jsonBody();
    if (body.contains("datasets")) {
        json dataset = body["datasets"];
        for (auto &[key, val]: dataset.items()) {
            auto dbNames = val.get<vector<string>>();
            for (auto &name: dbNames) {
                _dbManager->loadDataset(key, name);
            }
        }
    }
    return request.respondWithOK();
}

int Dispatcher::handlePOSTGetAllDocumentIDs(Request &request) {
    json body = request.jsonBody();
    auto dbName = body["database"].get<string>();
    auto colNames = body["collections"].get<vector<string>>();

    auto db = _dbManager->database(dbName);
    if (!db) {
        throw std::runtime_error("database not found");
    }

    json result = json::object();
    for (auto &colName: colNames) {
        CBLError error{};
        auto spec = CollectionSpec(colName);
        auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
        checkError(error);

        if (col) {
            CBLQuery *query = nullptr;
            CBLResultSet *rs = nullptr;

            DEFER {
                      CBLResultSet_Release(rs);
                      CBLQuery_Release(query);
                      CBLCollection_Release(col);
                  };

            string str = "SELECT meta().id FROM " + colName;
            query = CBLDatabase_CreateQuery(db, kCBLN1QLLanguage, FLS(str), nullptr, &error);
            checkError(error);

            rs = CBLQuery_Execute(query, &error);
            checkError(error);

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

    string id = _dbManager->startReplicator(params, reset);

    json result;
    result["id"] = id;
    return request.respondWithJSON(result);
}

static const string kStatuses[5] = {"STOPPED", "OFFLINE", "CONNECTING", "IDLE", "BUSY"};

int Dispatcher::handlePOSTGetReplicatorStatus(Request &request) {
    json body = request.jsonBody();

    auto id = body["id"].get<string>();
    auto repl = _dbManager->replicator(id);
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