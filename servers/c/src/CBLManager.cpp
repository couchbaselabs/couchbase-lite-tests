#include "CBLManager.h"
#include "CollectionSpec.h"
#include "support/Defer.h"
#include "support/Define.h"
#include "support/Exception.h"
#include "support/Zip.h"

#include <filesystem>
#include <fstream>
#include <utility>

using namespace std;
using namespace filesystem;
using namespace ts_support::exception;

#define DB_FILE_EXT ".cblite2"
#define DB_FILE_ZIP_EXT ".cblite2.zip"
#define DB_FILE_ZIP_EXTRACTED_DIR "extracted"
#define ASSET_DATASET_DIR "dataset"
#define ASSET_CERT_FILE "cert/cert.pem"

CBLManager::CBLManager(string databaseDir, string assetDir) {
    _databaseDir = std::move(databaseDir);
    _assetDir = std::move(assetDir);
//    logger::init(logger::LogLevel::info);
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

    // Release all replicators, their collections, and document listener tokens:
    {
        auto it = _contextMaps.begin();
        while (it != _contextMaps.end()) {
            auto &context = it->second;
            auto config = CBLReplicator_Config(context->replicator);
            for (int i = 0; i < config->collectionCount; i++) {
                auto replCol = config->collections[i];
                CBLCollection_Release(replCol.collection);
            }
            CBLReplicator_Release(context->replicator);
            CBLListener_Remove(context->token);
            it++;
        }
        _contextMaps.clear();
    }
}

void CBLManager::loadDataset(const string &name, const string &targetDatabaseName) {
    lock_guard<mutex> lock(_mutex);
    if (auto i = _databases.find(targetDatabaseName); i != _databases.end()) {
        return;
    }

    string fromDbPath;
    auto dbAssetPath = path(_assetDir).append(ASSET_DATASET_DIR);
    auto zipFilePath = path(dbAssetPath).append(name + DB_FILE_ZIP_EXT);

    auto p = zipFilePath.string();

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

FLSliceResult CBLManager::getServerCert() {
    auto certPath = path(_assetDir).append(ASSET_CERT_FILE);
    ifstream ifs(certPath.string(), ios::in | ios::binary);
    DEFER {
              ifs.close();
          };
    ifs.exceptions(ifstream::failbit | ifstream::badbit);
    ifs.seekg(0, ios::end);

    auto length = ifs.tellg();
    ifs.seekg(0, ios::beg);

    auto result = FLSliceResult_New(length);
    ifs.read((char *) result.buf, length);
    return result;
}

std::string CBLManager::startReplicator(const ReplicatorParams &params, bool reset) {
    lock_guard<mutex> lock(_mutex);
    auto db = databaseUnlocked(params.database);

    CBLError error{};
    vector<CBLReplicationCollection> replCols;

    bool success = false;
    DEFER {
              if (!success) {
                  for (auto &replCol: replCols) {
                      CBLCollection_Release(replCol.collection);
                  }
              }
          };

    auto context = make_unique<ReplicatorContext>();
    context->manager = this;

    for (auto &replColSpec: params.collections) {
        auto spec = CollectionSpec(replColSpec.collection);
        auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
        CheckError(error);
        CheckNotNull(col, "Collection " + spec.fullName() + " Not Found");

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
                throw RequestError("Cannot find push filter named " + pushFilter->name);
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
                throw RequestError("Cannot find pull filter named " + pullFilter->name);
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
    config.context = context.get();
    config.endpoint = endpoint;
    config.collections = replCols.data();
    config.collectionCount = replCols.size();
    config.replicatorType = params.replicatorType;
    config.continuous = params.continuous;
    config.authenticator = auth;

    FLSliceResult cert = FLSliceResult_CreateWith(nullptr, 0);
    if (params.endpoint.compare(0, 6, "wss://") == 0 && params.enablePinCert) {
        cert = getServerCert();
        config.pinnedServerCertificate = FLSliceResult_AsSlice(cert);
    }
    DEFER {
              FLSliceResult_Release(cert);
          };

    CBLReplicator *repl = CBLReplicator_Create(&config, &error);
    CheckError(error);

    string id = "@replicator::" + to_string(++_replicatorID);
    context->replicatorID = id;
    context->replicator = repl;

    if (params.enableDocumemntListener) {
        auto token = CBLReplicator_AddDocumentReplicationListener(repl, [](void *ctx,
                                                                           CBLReplicator *r,
                                                                           bool isPush,
                                                                           unsigned numDocuments,
                                                                           const CBLReplicatedDocument *documents) {
            vector<ReplicatedDocument> docs{};
            for (int i = 0; i < numDocuments; i++) {
                ReplicatedDocument doc{};
                doc.isPush = isPush;
                doc.collection = CollectionSpec(STR(documents[i].scope), STR(documents[i].collection)).fullName();
                doc.documentID = STR(documents[i].ID);
                doc.flags = documents[i].flags;
                doc.error = documents[i].error;
                docs.push_back(doc);
            }
            auto context = (ReplicatorContext *) ctx;
            context->manager->addDocumentReplication(context->replicatorID, docs);
        }, context.get());
        context->token = token;
    }

    _contextMaps[id] = std::move(context);

    CBLReplicator_Start(repl, reset);

    success = true;
    return id;
}

CBLReplicator *CBLManager::replicator(const string &id) {
    lock_guard<mutex> lock(_mutex);
    if (_contextMaps.find(id) == _contextMaps.end()) {
        return nullptr;
    }
    return _contextMaps[id]->replicator;
}

void CBLManager::addDocumentReplication(const std::string &id, const vector<ReplicatedDocument> &docs) {
    lock_guard<mutex> lock(_mutex);
    if (_contextMaps.find(id) != _contextMaps.end()) {
        _contextMaps[id]->replicatedDocs.push_back(docs);
    }
}

std::optional<CBLManager::ReplicatorStatus> CBLManager::status(const std::string &id) {
    lock_guard<mutex> lock(_mutex);
    if (_contextMaps.find(id) != _contextMaps.end()) {
        ReplicatorStatus result{};
        result.status = CBLReplicator_Status(_contextMaps[id]->replicator);
        if (_contextMaps[id]->token) {
            result.replicatedDocs = _contextMaps[id]->replicatedDocs;
            _contextMaps[id]->replicatedDocs = {};
        }
        return result;
    }
    return nullopt;
}
