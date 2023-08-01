#pragma once

#include "CBLReplicationFilter.h"

#include "support/CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)
#include FLEECE_HEADER(Fleece.h)

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
    static std::string version() { return CBLITE_VERSION; }

    static int buildNumber() { return CBLITE_BUILD_NUMBER; }

    static std::string edition() {
#ifdef COUCHBASE_ENTERPRISE
        return "Enterprise";
#else
        return "Community";
#endif
    }

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
        bool enablePinCert{false};
        bool enableDocumemntListener{false};
    };

    struct ReplicatedDocument {
        bool isPush{false};
        std::string collection;
        std::string documentID;
        CBLDocumentFlags flags{0};
        CBLError error{};
    };

    struct ReplicatorStatus {
        CBLReplicatorStatus status;
        std::optional<std::vector<std::vector<ReplicatedDocument>>> replicatedDocs;
    };

    std::string startReplicator(const ReplicatorParams &params, bool reset);

    CBLReplicator *replicator(const std::string &id);

    std::optional<ReplicatorStatus> status(const std::string &id);

private:
    CBLDatabase *databaseUnlocked(const std::string &name);

    FLSliceResult getServerCert();

    void addDocumentReplication(const std::string &id, const std::vector<ReplicatedDocument> &docs);

    std::mutex _mutex;

    std::string _databaseDir;
    std::string _assetDir;

    /** Map of database id and database */
    std::unordered_map<std::string, CBLDatabase *> _databases;

    /* Replicator id number */
    int64_t _replicatorID = 0;

    /** Replicator context for keeping per replicator objects and being referenced by callbacks */
    struct ReplicatorContext {
        /** CBLManager Object */
        CBLManager *manager{nullptr};

        /** Replicator ID */
        std::string replicatorID;

        /** Replicator */
        CBLReplicator *replicator{nullptr};

        /** Document Listener Token */
        CBLListenerToken *token{nullptr};

        /** Map of collection name and replication filter object */
        std::unordered_map<std::string, std::unique_ptr<ReplicationFilter>> filters{};

        /** Replicated Documents in batch */
        std::vector<std::vector<ReplicatedDocument>> replicatedDocs{};
    };

    std::unordered_map<std::string, std::unique_ptr<ReplicatorContext>> _contextMaps;
};
