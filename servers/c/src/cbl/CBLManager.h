#pragma once

// CBL
#include "CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)
#include FLEECE_HEADER(Fleece.h)
#include "CBLReplicationFilter.h"
#include "CBLReplicatorParams.h"
#include "Snapshot.h"

// lib
#include <mutex>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

struct CBLDatabase;

namespace ts::cbl {
    class CBLManager {
    public:
        /// Constructor

        CBLManager(const std::string &databaseDir, const std::string &assetDir);

        /// Database

        void reset();

        void loadDataset(const std::string &name, const std::string &targetDatabaseName);

        /**
         * Get the loaded database. The database instance is managed by the CBLManager.
         * Do not release the database instance unless the object is additionally retained. */
        CBLDatabase *database(const std::string &name);

        static CBLCollection *collection(const CBLDatabase *db, const std::string &name, bool mustExist = true);

        static const CBLDocument *
        document(const CBLDatabase *db, const std::string &collectionName, const std::string &id);

        /// Replicator

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

        std::optional<ReplicatorStatus> replicatorStatus(const std::string &id);

        /// Snapshot

        Snapshot *createSnapshot();

        Snapshot *snapshot(const std::string &id);

        void deleteSnapshot(const std::string &id);

    private:
        CBLDatabase *databaseUnlocked(const std::string &name);

        FLSliceResult getServerCert();

        void addDocumentReplication(const std::string &id, const std::vector<ReplicatedDocument> &docs);

        std::mutex _mutex;

        std::string _databaseDir;
        std::string _assetDir;

        /** Map of dataset name and extracted dataset path */
        std::unordered_map<std::string, std::string> _extDatasetPaths;

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
            std::unordered_map<std::string, std::unique_ptr<ReplicationFilter>> filters;

            /** Replicated Documents in batch */
            std::vector<std::vector<ReplicatedDocument>> replicatedDocs;
        };

        std::unordered_map<std::string, std::unique_ptr<ReplicatorContext>> _contextMaps;

        std::unordered_map<std::string, std::unique_ptr<Snapshot>> _snapShots;
    };
}