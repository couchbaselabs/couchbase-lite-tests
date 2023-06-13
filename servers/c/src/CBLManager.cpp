#include "CBLManager.h"
#include "CollectionSpec.h"
#include "support/Defer.h"
#include "support/Define.h"
#include "support/Exception.h"
#include "support/Zip.h"

#include <filesystem>
#include <utility>

using namespace filesystem;
using namespace std;
using namespace ts_support::exception;

#define DB_FILE_EXT ".cblite2"
#define DB_FILE_ZIP_EXT ".cblite2.zip"
#define DB_FILE_ZIP_EXTRACTED_DIR "extracted"
#define ASSET_DATABASES_DIR "databases"

CBLManager::CBLManager(string databaseDir, string assetDir) {
    _databaseDir = std::move(databaseDir);
    _assetDir = std::move(assetDir);
}

void CBLManager::reset() {
    lock_guard<mutex> lock(_mutex);

    // Delete and release all databases:
    {
        auto it = _databases.begin();
        while (it != _databases.end()) {
            CBLDatabase *db = it->second;
            DEFER { CBLDatabase_Release(db); };

            CBLError error{};
            if (!CBLDatabase_Delete(db, &error)) {
                // What to do with the rest?
                throw CBLException(error);
            }
            it++;
        }
        _databases.clear();
    }

    // Release all replicators and their collections:
    {
        auto it = _replicators.begin();
        while (it != _replicators.end()) {
            CBLReplicator *repl = it->second;
            auto config = CBLReplicator_Config(repl);
            for (int i = 0; i < config->collectionCount; i++) {
                auto replCol = config->collections[i];
                CBLCollection_Release(replCol.collection);
            }
            CBLReplicator_Release(repl);
            it++;
        }
        _replicators.clear();
        _contexts.clear();
    }
}

void CBLManager::loadDataset(const string &name, const string &targetDatabaseName) {
    lock_guard<mutex> lock(_mutex);
    if (auto i = _databases.find(targetDatabaseName); i != _databases.end()) {
        return;
    }

    string fromDbPath;
    auto dbAssetPath = path(_assetDir).append(ASSET_DATABASES_DIR);
    auto zipFilePath = path(dbAssetPath).append(name + DB_FILE_ZIP_EXT);
    if (filesystem::exists(zipFilePath)) {
        auto extDirPath = path(_databaseDir).append(DB_FILE_ZIP_EXTRACTED_DIR);
        ts_support::zip::extractZip(zipFilePath.string(), extDirPath.string());
        fromDbPath = extDirPath.append(name + DB_FILE_EXT).string();
    } else {
        fromDbPath = dbAssetPath.append(name + DB_FILE_EXT).string();
    }

    CBLError error{};
    CBLDatabaseConfiguration config = {FLS(_databaseDir)};
    if (CBL_DatabaseExists(FLS(targetDatabaseName), config.directory)) {
        if (!CBL_DeleteDatabase(FLS(targetDatabaseName), config.directory, &error)) {
            throw CBLException(error);
        }
    }

    if (!CBL_CopyDatabase(FLS(fromDbPath), FLS(targetDatabaseName), &config, &error)) {
        throw CBLException(error);
    }

    CBLDatabase *db = CBLDatabase_Open(FLS(targetDatabaseName), &config, &error);
    if (!db) {
        throw CBLException(error);
    }
    _databases[targetDatabaseName] = db;
}

CBLDatabase *CBLManager::database(const string &name) {
    lock_guard<mutex> lock(_mutex);
    return databaseUnlocked(name);
}

CBLDatabase *CBLManager::databaseUnlocked(const string &name) {
    CBLDatabase *db = nullptr;
    if (auto i = _databases.find(name); i != _databases.end()) {
        db = i->second;
    }
    CheckNotNull(db, "Database '" + name + "' Not Found");
    return db;
}

CBLCollection *CBLManager::collection(const CBLDatabase *db, const std::string &name, bool mustExist) {
    CBLError error{};
    auto spec = CollectionSpec(name);
    auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
    CheckError(error);
    if (mustExist) {
        CheckNotNull(col, "Collection Not Found");
    }
    return col;
}

std::string CBLManager::startReplicator(const ReplicatorParams &params, bool reset) {
    lock_guard<mutex> lock(_mutex);
    auto db = databaseUnlocked(params.database);

    CBLError error{};
    vector<CBLReplicationCollection> replCols;

    DEFER {
              if (error.code > 0) {
                  for (auto &replCol: replCols) {
                      CBLCollection_Release(replCol.collection);
                  }
              }
          };

    auto context = make_unique<ReplicatorContext>();

    for (auto &replColSpec: params.collections) {
        auto spec = CollectionSpec(replColSpec.collection);
        auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
        if (error.code > 0) {
            break;
        }

        CBLReplicationCollection replCol{};
        replCol.collection = col;

        // Channels:
        if (!replColSpec.channels.empty()) {
            auto channels = FLMutableArray_New();
            for (auto &channel: replColSpec.channels) {
                FLMutableArray_AppendString(channels, FLS(channel));
            }
            replCol.channels = channels;
        }

        // documentIDs:
        if (!replColSpec.documentIDs.empty()) {
            auto docIDs = FLMutableArray_New();
            for (auto &docID: replColSpec.documentIDs) {
                FLMutableArray_AppendString(docIDs, FLS(docID));
            }
            replCol.documentIDs = docIDs;
        }

        // Push Filter:
        auto pushFilter = replColSpec.pushFilter;
        if (pushFilter) {
            auto filter = ReplicationFilter::make_filter(pushFilter.value());
            if (!filter) {
                throw domain_error("Cannot find push filter named " + pushFilter->name);
            }
            context->filters[replColSpec.collection] = unique_ptr<ReplicationFilter>(filter);
            replCol.pushFilter = [](void *ctx, CBLDocument *doc, CBLDocumentFlags flags) -> bool {
                auto collectionName = CollectionSpec(CBLDocument_Collection(doc)).fullName();
                return ((ReplicatorContext *) ctx)->filters[collectionName].get()->run(doc, flags);
            };
        }

        // Pull Filter:
        auto pullFilter = replColSpec.pullFilter;
        if (pullFilter) {
            auto filter = ReplicationFilter::make_filter(pullFilter.value());
            if (!filter) {
                throw domain_error("Cannot find pull filter named " + pullFilter->name);
            }
            context->filters[replColSpec.collection] = unique_ptr<ReplicationFilter>(filter);
            replCol.pullFilter = [](void *ctx, CBLDocument *doc, CBLDocumentFlags flags) -> bool {
                auto collectionName = CollectionSpec(CBLDocument_Collection(doc)).fullName();
                return ((ReplicatorContext *) ctx)->filters[collectionName].get()->run(doc, flags);
            };
        }
        replCols.push_back(replCol);
    }

    CBLEndpoint *endpoint = nullptr;
    CBLAuthenticator *auth = nullptr;
    DEFER {
              CBLEndpoint_Free(endpoint);
              CBLAuth_Free(auth);
          };

    endpoint = CBLEndpoint_CreateWithURL(FLS(params.endpoint), &error);
    CheckError(error);

    if (params.authenticator) {
        auth = CBLAuth_CreatePassword(FLS(params.authenticator->username),
                                      FLS(params.authenticator->password));
    }

    CBLReplicatorConfiguration config{};
    config.endpoint = endpoint;
    config.collections = replCols.data();
    config.collectionCount = replCols.size();
    config.replicatorType = params.replicatorType;
    config.continuous = params.continuous;
    config.authenticator = auth;
    config.context = context.get();

    CBLReplicator *repl = CBLReplicator_Create(&config, &error);
    CheckError(error);
    CBLReplicator_Start(repl, reset);

    _contexts.push_back(std::move(context));

    string id = "@replicator::" + to_string(++replicatorID);
    _replicators[id] = repl;
    return id;
}

CBLReplicator *CBLManager::replicator(const string &id) {
    lock_guard<mutex> lock(_mutex);
    return _replicators[id];
}
