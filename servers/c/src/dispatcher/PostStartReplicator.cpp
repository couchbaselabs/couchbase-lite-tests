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

int Dispatcher::handlePOSTStartReplicator(Request &request, Session *session) {
    static constexpr const char *kAuthTypeBasic = "BASIC";

    json body = request.jsonBody();
    CheckBody(body);

    ReplicatorParams params;
    json config = GetValue<json>(body, "config");
    CheckIsObject(config, "config");

    params.endpoint = GetValue<string>(config, "endpoint");
    params.database = GetValue<string>(config, "database");

    auto replicatorType = GetValue<string>(config, "replicatorType", "pushAndPull");
    params.replicatorType = ReplicatorEnum.value(replicatorType);
    params.continuous = GetValue<bool>(config, "continuous", false);

    auto auth = GetOptValue<json>(config, "authenticator");
    if (auth) {
        auto authObject = auth.value();
        CheckIsObject(authObject, "authenticator");
        auto authTypeValue = GetValue<string>(authObject, "type");
        auto authType = AuthTypeEnum.value(authTypeValue);
        if (authType == AuthType::basic) {
            auto username = GetValue<string>(authObject, "username");
            auto password = GetValue<string>(authObject, "password");
            params.authenticator = make_unique<BasicAuthenticator>(username, password);
        } else if (authType == AuthType::session) {
            auto sessionID = GetValue<string>(authObject, "sessionID");
            auto cookieName = GetValue<string>(authObject, "cookieName");
            params.authenticator = make_unique<SessionAuthenticator>(sessionID, cookieName);
        } else {
            throw RequestError("Unsupported authenticator");
        }
    }

    params.enableDocumemntListener = GetValue<bool>(config, "enableDocumentListener", false);
    params.enableAutoPurge = GetValue<bool>(config, "enableAutoPurge", false);
    params.pinnedServerCert = GetOptValue<string>(config, "pinnedServerCert");
    params.headers = GetOptValue<unordered_map<string, string>>(config, "headers");

    vector<ReplicationCollection> collections;
    for (auto &colObject: GetValue<vector<json>>(config, "collections")) {
        vector<string> names = GetValue<vector<string>>(colObject, "names");
        if (names.empty()) {
            throw RequestError("No collections specified");
        }

        for (auto &name: names) {
            ReplicationCollection col;
            col.collection = name;
            col.channels = GetOptValue<vector<string>>(colObject, "channels");
            col.documentIDs = GetOptValue<vector<string>>(colObject, "documentIDs");

            auto pushFilter = GetOptValue<json>(colObject, "pushFilter");
            if (pushFilter) {
                auto filterObject = pushFilter.value();
                ReplicationFilterSpec spec{};
                spec.name = GetValue<string>(filterObject, "name");
                spec.params = GetValue<json>(filterObject, "params", json::object());
                col.pushFilter = spec;
            }

            auto pullFilter = GetOptValue<json>(colObject, "pullFilter");
            if (pullFilter) {
                auto filterObject = pullFilter.value();
                ReplicationFilterSpec spec{};
                spec.name = GetValue<string>(filterObject, "name");
                spec.params = GetValue<json>(filterObject, "params", json::object());
                col.pullFilter = spec;
            }

            auto conflictResolver = GetOptValue<json>(colObject, "conflictResolver");
            if (conflictResolver) {
                auto conflictResolverObject = conflictResolver.value();
                ConflictResolverSpec spec{};
                spec.name = GetValue<string>(conflictResolverObject, "name");
                spec.params = GetValue<json>(conflictResolverObject, "params", json::object());
                col.conflictResolver = spec;
            }

            collections.push_back(col);
        }
    }

    params.collections = collections;

    bool reset = GetValue<bool>(body, "reset", false);
    string id = session->cblManager()->startReplicator(params, reset);

    json result;
    result["id"] = id;
    return request.respondWithJSON(result);
}
