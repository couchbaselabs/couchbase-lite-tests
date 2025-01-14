#pragma once

// CBL
#include "CBLHeader.h"
#include CBL_HEADER(CBLReplicator.h)
#include "CBLReplicationFilter.h"
#include "Define.h"

#include <optional>
#include <string>
#include <vector>

namespace ts::cbl {
    struct ReplicationCollection;

    struct ReplicationAuthenticator {
    public:
        virtual ~ReplicationAuthenticator() = default;
        virtual CBLAuthenticator* toCBLAuth() const = 0;
    };

    struct BasicAuthenticator: ReplicationAuthenticator {
    public:
        BasicAuthenticator(const std::string& user, const std::string& pass)
            : username(user), password(pass) { }

        CBLAuthenticator* toCBLAuth() const override {
            return CBLAuth_CreatePassword(FLS(username), FLS(password));
        }
    private:
        std::string username;
        std::string password;
    };

    struct SessionAuthenticator : public ReplicationAuthenticator {
    public:
        // Constructor to initialize private members
        SessionAuthenticator(const std::string &session, const std::string &cookie)
            : sessionID(session), cookieName(cookie) { }

        CBLAuthenticator* toCBLAuth() const override {
            return CBLAuth_CreateSession(FLS(sessionID), FLS(cookieName));
        }
    private:
        std::string sessionID;
        std::string cookieName;
    };

    struct ReplicatorParams {
        std::string database;
        std::vector<ReplicationCollection> collections;
        std::string endpoint;
        CBLReplicatorType replicatorType{kCBLReplicatorTypePushAndPull};
        bool continuous{false};
        std::unique_ptr<ReplicationAuthenticator> authenticator;
        bool enablePinCert{false};
        bool enableDocumemntListener{false};
        bool enableAutoPurge{true};
        std::optional<std::string> pinnedServerCert;
    };

    struct ReplicationCollection {
        std::string collection;
        std::optional<std::vector<std::string>> channels;
        std::optional<std::vector<std::string>> documentIDs;
        std::optional<ReplicationFilterSpec> pushFilter;
        std::optional<ReplicationFilterSpec> pullFilter;
        std::optional<ConflictResolverSpec> conflictResolver;
    };
}
