#pragma once

// CBL
#include "CBLHeader.h"
#include CBL_HEADER(CBLReplicator.h)
#include "CBLReplicationFilter.h"

#include <optional>
#include <string>
#include <vector>

namespace ts::cbl {
    struct ReplicationCollection;

    struct ReplicationAuthenticator {
        std::string username;
        std::string password;
    };

    struct ReplicatorParams {
        std::string database;
        std::vector<ReplicationCollection> collections;
        std::string endpoint;
        CBLReplicatorType replicatorType{kCBLReplicatorTypePushAndPull};
        bool continuous{false};
        std::optional<ReplicationAuthenticator> authenticator;
        bool enablePinCert{false};
        bool enableDocumemntListener{false};
        bool enableAutoPurge{true};
        std::optional<std::string> pinnedServerCert;
    };

    struct ReplicationCollection {
        std::string collection;
        std::vector<std::string> channels;
        std::vector<std::string> documentIDs;
        std::optional<ReplicationFilterSpec> pushFilter;
        std::optional<ReplicationFilterSpec> pullFilter;
        std::optional<ConflictResolverSpec> conflictResolver;
    };
}
