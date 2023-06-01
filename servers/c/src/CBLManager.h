#pragma once

#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <optional>
#include <mutex>

#include "cbl/CouchbaseLite.h"

struct CBLDatabase;

class CBLManager {
public:
    CBLManager(std::string databaseDir, std::string assetDir);

    void reset();

    void loadDataset(const std::string &name, const std::string &targetDatabaseName);

    /**
     * Get the loaded database. The database instance is managed by the CBLManager.
     * Do not release the database instance unless the object is additionally retained.
     */
    CBLDatabase *database(const std::string &name);

    static CBLCollection *collection(const CBLDatabase *db, const std::string &name, bool mustExist = true);

    struct ReplicationCollection {
        std::string collection;
        std::vector<std::string> channels;
        std::vector<std::string> documentIDs;
    };

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
    };

    std::string startReplicator(const ReplicatorParams &params, bool reset);

    CBLReplicator *replicator(const std::string &id);

private:
    CBLDatabase *databaseUnlocked(const std::string &name);

    std::mutex _mutex;

    std::string _databaseDir;
    std::string _assetDir;

    std::unordered_map<std::string, CBLDatabase *> _databases;

    int64_t replicatorID = 0;
    std::unordered_map<std::string, CBLReplicator *> _replicators;
};
