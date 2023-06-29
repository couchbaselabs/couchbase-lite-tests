#pragma once

#include "CBLReplicationFilter.h"

#include "support/CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)

#include <mutex>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

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
        std::optional<ReplicationFilterSpec> pushFilter;
        std::optional<ReplicationFilterSpec> pullFilter;
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

    /** Map of database id and database */
    std::unordered_map<std::string, CBLDatabase *> _databases;

    /* Replicator id number */
    int64_t replicatorID = 0;

    /** Map of replicator id and database object */
    std::unordered_map<std::string, CBLReplicator *> _replicators;

    /** Replicator context for keeping per replicator objects used by callbacks */
    struct ReplicatorContext {
        /** Map of collection name and replication filter object */
        std::unordered_map<std::string, std::unique_ptr<ReplicationFilter>> filters;
    };

    /** Vector for keeping replicator contexts. */
    std::vector<std::unique_ptr<ReplicatorContext>> _contexts;
};
