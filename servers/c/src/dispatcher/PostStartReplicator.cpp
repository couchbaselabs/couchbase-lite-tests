#include "Dispatcher+Common.h"

namespace ts {
    static auto ReplicatorEnum = StringEnum<CBLReplicatorType>(
        {
            "pushAndPull",
            "push",
            "pull"
        },
        {
            kCBLReplicatorTypePushAndPull,
            kCBLReplicatorTypePush,
            kCBLReplicatorTypePull
        }
    );

    enum class AuthType {
        basic, session
    };

    static auto AuthTypeEnum = StringEnum<AuthType>(
        {
            "basic",
            "session"
        },
        {
            AuthType::basic,
            AuthType::session
        }
    );
}

int Dispatcher::handlePOSTStartReplicator(Request &request) {
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
        params.replicatorType = ReplicatorEnum.value(replicatorType);
    }

    if (config.contains("continuous")) {
        params.continuous = GetValue<bool>(config, "continuous");
    }

    if (config.contains("authenticator")) {
        json authObject = config["authenticator"];
        CheckIsObject(authObject, "authenticator");
        auto authTypeValue = GetValue<string>(authObject, "type");
        auto authType = AuthTypeEnum.value(authTypeValue);
        if (authType == AuthType::basic) {
            ReplicationAuthenticator auth;
            auth.username = GetValue<string>(authObject, "username");
            auth.password = GetValue<string>(authObject, "password");
            params.authenticator = auth;
        } else {
            throw RequestError("Not support session authenticator");
        }
    }

    if (config.contains("enableDocumentListener")) {
        params.enableDocumemntListener = GetValue<bool>(config, "enableDocumentListener");
    }

    if (config.contains("enableAutoPurge")) {
        params.enableAutoPurge = GetValue<bool>(config, "enableAutoPurge");
    }

    if (config.contains("pinnedServerCert")) {
        params.pinnedServerCert = GetValue<string>(config, "pinnedServerCert");
    }

    vector<ReplicationCollection> collections;
    for (auto &colObject: GetValue<vector<json>>(config, "collections")) {
        vector<string> names;
        if (colObject.contains("names")) {
            names = GetValue<vector<string>>(colObject, "names");
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
                ReplicationFilterSpec spec{};
                spec.name = GetValue<string>(filterObject, "name");
                spec.params = filterObject.contains("params") ?
                              GetValue<json>(filterObject, "params") : json::object();
                col.pushFilter = spec;
            }

            if (colObject.contains("pullFilter")) {
                auto filterObject = GetValue<json>(colObject, "pullFilter");
                ReplicationFilterSpec spec{};
                spec.name = GetValue<string>(filterObject, "name");
                spec.params = filterObject.contains("params") ?
                              GetValue<json>(filterObject, "params") : json::object();
                col.pullFilter = spec;
            }
            
            if (colObject.contains("conflictResolver")) {
                auto conflictResolver = GetValue<json>(colObject, "conflictResolver");
                ConflictResolverSpec spec{};
                spec.name = GetValue<string>(conflictResolver, "name");
                spec.params = conflictResolver.contains("params") ?
                              GetValue<json>(conflictResolver, "params") : json::object();
                col.conflictResolver = spec;
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
