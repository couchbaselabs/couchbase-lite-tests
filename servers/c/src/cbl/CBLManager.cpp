#include "CBLManager.h"
#include "CollectionSpec.h"

// support
#include "Defer.h"
#include "Define.h"
#include "Error.h"
#include "Precondition.h"
#include "StringUtil.h"
#include "ZipUtil.h"

// lib
#include <filesystem>
#include <fstream>
#include <utility>

using namespace std;
using namespace filesystem;

using namespace ts::support;
using namespace ts::support::precond;
using namespace ts::support::error;

#define DB_FILE_EXT ".cblite2"
#define DB_FILE_ZIP_EXT ".cblite2.zip"
#define DB_FILE_ZIP_EXTRACTED_DIR "extracted"
#define ASSET_DBS_DIR "dbs"
#define ASSET_BLOBS_DIR "blobs"
#define ASSET_CERT_FILE "cert/cert.pem"

namespace ts::cbl {
    /// Constructor

    CBLManager::CBLManager(const string &databaseDir, const string &assetDir) {
        _databaseDir = databaseDir;
        _assetDir = assetDir;
    }

    /// Database

    void CBLManager::reset() {
        lock_guard <mutex> lock(_mutex);

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
        auto dbAssetPath = path(_assetDir).append(ASSET_DBS_DIR);
        auto zipFilePath = path(dbAssetPath).append(name + DB_FILE_ZIP_EXT);
        if (filesystem::exists(zipFilePath)) {
            if (auto it = _extDatasetPaths.find(name); it != _extDatasetPaths.end()) {
                fromDbPath = it->second;
            } else {
                auto extDirPath = path(_databaseDir).append(DB_FILE_ZIP_EXTRACTED_DIR);
                zip::extractZip(zipFilePath.string(), extDirPath.string());
                fromDbPath = extDirPath.append(name + DB_FILE_EXT).string();
                _extDatasetPaths[name] = fromDbPath;
            }
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
        if (auto it = _databases.find(name); it != _databases.end()) {
            db = it->second;
        }
        checkNotNull(db, "Database '" + name + "' Not Found");
        return db;
    }

    CBLCollection *CBLManager::collection(const CBLDatabase *db, const string &name, bool mustExist) {
        CBLError error{};
        auto spec = CollectionSpec(name);
        auto col = CBLDatabase_Collection(db, FLS(spec.name()), FLS(spec.scope()), &error);
        checkCBLError(error);
        if (mustExist) {
            checkNotNull(col, "Collection Not Found");
        }
        return col;
    }

    const CBLDocument *CBLManager::document(const CBLDatabase *db, const string &collectionName, const string &id) {
        auto collection = CBLManager::collection(db, collectionName);
        CBLError error{};
        auto doc = CBLCollection_GetDocument(collection, FLS(id), &error);
        checkCBLError(error);
        return doc;
    }

    /// Blob

    bool CBLManager::blobExists(const CBLDatabase *db, FLDict blobDict) {
        CBLError error{};
        auto blob = CBLDatabase_GetBlob(const_cast<CBLDatabase *>(db), blobDict, &error);
        DEFER { CBLBlob_Release(blob); };
        checkCBLError(error);
        return (blob != nullptr);
    }

    std::string blobContentType(const string &name) {
        auto comps = str::split(name, '.');
        auto ext = comps.back();
        if (ext == "jpg") {
            return "image/jpeg";
        }
        return "application/octet-stream";
    }

    CBLBlob *CBLManager::blob(const string &name, CBLDatabase *db) {
        auto blobPath = path(_assetDir).append(ASSET_BLOBS_DIR).append(name);
        ifstream ifs(blobPath.string(), ios::in | ios::binary);
        if (!ifs.is_open()) {
            throw logic_error("Blob '" + name + "' not found in dataset");
        }
        DEFER { ifs.close(); };
        ifs.exceptions(ifstream::badbit);

        CBLError error{};
        auto ws = CBLBlobWriter_Create(db, &error);\
        checkCBLError(error);

        const size_t bufferSize = 4096;
        char buffer[bufferSize];
        while (!ifs.eof()) {
            ifs.read(buffer, bufferSize);
            if (!CBLBlobWriter_Write(ws, buffer, ifs.gcount(), &error)) {
                CBLBlobWriter_Close(ws);
                checkCBLError(error);
            }
        }

        auto contentType = blobContentType(name);
        return CBLBlob_CreateWithStream(FLS(contentType), ws);
    }

    /// Replicator

    FLSliceResult CBLManager::getServerCert() {
        auto certPath = path(_assetDir).append(ASSET_CERT_FILE);
        ifstream ifs(certPath.string(), ios::in | ios::binary);
        DEFER { ifs.close(); };

        ifs.exceptions(ifstream::failbit | ifstream::badbit);
        ifs.seekg(0, ios::end);

        auto length = ifs.tellg();
        ifs.seekg(0, ios::beg);

        auto result = FLSliceResult_New(length);
        ifs.read((char *) result.buf, length);
        return result;
    }

    std::string CBLManager::startReplicator(const ReplicatorParams &params, bool reset) {
        lock_guard <mutex> lock(_mutex);
        auto db = databaseUnlocked(params.database);

        CBLError error{};
        vector <CBLReplicationCollection> replCols;

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
            checkCBLError(error);
            checkNotNull(col, "Collection " + spec.fullName() + " Not Found");

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
                    throw logic_error("Cannot find push filter named " + pushFilter->name);
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
                    throw logic_error("Cannot find pull filter named " + pullFilter->name);
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
        checkCBLError(error);

        if (params.authenticator) {
            auth = CBLAuth_CreatePassword(FLS(params.authenticator->username),
                                          FLS(params.authenticator->password));
        }

        CBLReplicatorConfiguration config{};
        config.context = context.get();
        config.endpoint = endpoint;
        if (!replCols.empty()) {
            config.collections = replCols.data();
            config.collectionCount = replCols.size();
        } else {
            config.database = db;
        }
        config.replicatorType = params.replicatorType;
        config.continuous = params.continuous;
        config.authenticator = auth;
        config.disableAutoPurge = !params.enableAutoPurge;

        FLSliceResult cert = FLSliceResult_CreateWith(nullptr, 0);
        if (params.endpoint.compare(0, 6, "wss://") == 0 && params.enablePinCert) {
            cert = getServerCert();
            config.pinnedServerCertificate = FLSliceResult_AsSlice(cert);
        }
        DEFER { FLSliceResult_Release(cert); };

        CBLReplicator *repl = CBLReplicator_Create(&config, &error);
        checkCBLError(error);

        string id = "@replicator::" + to_string(++_replicatorID);
        context->replicatorID = id;
        context->replicator = repl;

        if (params.enableDocumemntListener) {
            auto token = CBLReplicator_AddDocumentReplicationListener(repl, [](void *ctx,
                                                                               CBLReplicator *r,
                                                                               bool isPush,
                                                                               unsigned numDocuments,
                                                                               const CBLReplicatedDocument *documents) {
                vector <ReplicatedDocument> docs{};
                for (unsigned i = 0; i < numDocuments; i++) {
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

    void CBLManager::addDocumentReplication(const std::string &id, const vector <ReplicatedDocument> &docs) {
        lock_guard<mutex> lock(_mutex);
        if (_contextMaps.find(id) != _contextMaps.end()) {
            _contextMaps[id]->replicatedDocs.push_back(docs);
        }
    }

    std::optional<CBLManager::ReplicatorStatus> CBLManager::replicatorStatus(const std::string &id) {
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

    /// Snapshot

    Snapshot *CBLManager::createSnapshot() {
        lock_guard<mutex> lock(_mutex);
        auto s = new Snapshot();
        unique_ptr<Snapshot> snapshot{s};
        _snapShots[s->id()] = std::move(snapshot);
        return s;
    }

    Snapshot *CBLManager::snapshot(const string &id) {
        lock_guard<mutex> lock(_mutex);
        auto snapshot = _snapShots[id].get();
        checkNotNull(snapshot, "Snapshot '" + id + "' Not Found");
        return snapshot;
    }

    void CBLManager::deleteSnapshot(const string &id) {
        lock_guard<mutex> lock(_mutex);
        _snapShots.erase(id);
    }
}