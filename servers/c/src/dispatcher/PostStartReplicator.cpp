#include "Dispatcher+Common.h"

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
        if (EnumEquals(replicatorType, kReplicatorTypePush)) {
            params.replicatorType = kCBLReplicatorTypePush;
        } else if (EnumEquals(replicatorType, kReplicatorTypePull)) {
            params.replicatorType = kCBLReplicatorTypePull;
        } else if (EnumEquals(replicatorType, kReplicatorTypePushAndPull)) {
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
        auto authType = GetValue<string>(authObject, "type");
        if (EnumEquals(authType, kAuthTypeBasic)) {
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