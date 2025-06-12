//
//  DatabaseManager.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import CouchbaseLiteSwift
import ZipArchive

class DatabaseManager {
    private let kDatasetBaseURL = "https://media.githubusercontent.com/media/couchbaselabs/couchbase-lite-tests/refs/heads/main/dataset/server/"
    private let kDatasetDownloadDirectory = "downloads"
    private let kDatasetExtractedDirectory = "extracted"
    
    private let databaseDirectory: String
    private let datasetVersion: String
    
    private var databases : [ String : Database ] = [:]
    private var replicators : [ UUID : Replicator ] = [:]
    private var replicatorDocuments : [ UUID : [ContentTypes.DocumentReplication] ] = [:]
    
    
    public init(directory: String, datasetVersion: String) {
        self.databaseDirectory = directory
        self.datasetVersion = datasetVersion
    }
    
    deinit {
        do {
            try reset()
        } catch {
            Log.log(level: .error, message: "Failed to reset database manager : \(error)")
        }
    }
    
    @discardableResult
    public func addCollection(dbName: String, scope: String, name: String) throws -> Collection {
        Log.log(level: .debug, message: "Creating collection: \(scope).\(name) in database: \(dbName)")
        guard let database = databases[dbName]
        else {
            Log.log(level: .error, message: "Failed to create collection, database '\(dbName)' does not exist")
            throw TestServerError.cblDBNotOpen
        }
        
        do {
            let coll = try database.createCollection(name: name, scope: scope)
            Log.log(level: .debug, message: "Collection \(scope).\(name) successfully created in database \(dbName)")
            return coll
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to create collection due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func runQuery(dbName: String, queryString: String) throws -> ResultSet {
        Log.log(level: .debug, message: "Running query: `\(queryString)` in database: \(dbName)")
        guard let database = databases[dbName]
        else {
            Log.log(level: .error, message: "Failed to run query, database '\(dbName)' does not exist")
            throw TestServerError.cblDBNotOpen
        }
        
        do {
            let query = try database.createQuery(queryString)
            let result = try query.execute()
            Log.log(level: .debug, message: "Query successfully executed.")
            return result
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to run query due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func startReplicator(config: ContentTypes.ReplicatorConfiguration, reset: Bool) throws -> UUID {
        Log.log(level: .debug, message: "Starting Replicator with config: \(config.description)")
        
        guard let database = databases[config.database]
        else {
            Log.log(level: .error, message: "Failed to start Replicator, database '\(config.database)' does not exist")
            throw TestServerError.cblDBNotOpen
        }
        
        guard let endpointURL = URL(string: config.endpoint)
        else {
            Log.log(level: .error, message: "Failed to start Replicator, invalid endpoint URL.")
            throw TestServerError.badRequest("Endpoint URL is not a valid URL.")
        }
        
        var replConfig = ReplicatorConfiguration(target: URLEndpoint(url: endpointURL))
        
        switch(config.replicatorType) {
        case .push:
            replConfig.replicatorType = .push
        case .pull:
            replConfig.replicatorType = .pull
        case .pushpull:
            replConfig.replicatorType = .pushAndPull
        }
        
        replConfig.continuous = config.continuous
        
        replConfig.enableAutoPurge = config.enableAutoPurge
        
        if let auth = config.authenticator {
            replConfig.authenticator = try DatabaseManager.getCBLAuthenticator(from: auth)
        }
        
        if let pinnedCert = config.pinnedServerCert {
            guard let cert = CertUtil.certificate(from: pinnedCert) else {
                throw TestServerError.badRequest("Pinned server cert has invalid format.")
            }
            replConfig.pinnedServerCertificate = cert
        }
        
        if config.collections.count > 0 {
            for configColl in config.collections {
                let collections = try configColl.names.map({ collName in
                    guard let collection = try collection(collName, inDB: database)
                    else {
                        Log.log(level: .error, message: "Failed to start Replicator, Collection '\(collName)' does not exist in \(config.database).")
                        throw TestServerError.badRequest("Collection '\(collName)' does not exist in \(config.database).")
                    }
                    return collection
                })
                
                var collConfig = CollectionConfiguration()
                collConfig.channels = configColl.channels
                collConfig.documentIDs = configColl.documentIDs
                if let pullFilter = configColl.pullFilter {
                    collConfig.pullFilter = try DatabaseManager.getCBLReplicationFilter(from: pullFilter)
                }
                if let pushFilter = configColl.pushFilter {
                    collConfig.pushFilter = try DatabaseManager.getCBLReplicationFilter(from: pushFilter)
                }
                if let resolver = configColl.conflictResolver {
                    collConfig.conflictResolver = try DatabaseManager.getCBLReplicationConflictResolver(from: resolver)
                }
                replConfig.addCollections(collections, config: collConfig)
            }
        } else {
            replConfig.addCollection(try database.defaultCollection())
        }
        
        let replicatorID = UUID()
        
        let replicator = Replicator(config: replConfig)
        
        replicators[replicatorID] = replicator
        
        // Whenever a document is replicated, add it to the replicatorDocuments dict
        if(config.enableDocumentListener) {
            replicatorDocuments[replicatorID] = []
            replicator.addDocumentReplicationListener({ [weak self] docChange in
                guard self != nil
                else { return }
                for doc in docChange.documents {
                    var docFlags: [ContentTypes.DocumentReplicationFlags] = []
                    
                    switch doc.flags {
                    case .accessRemoved:
                        docFlags.append(.accessRemoved)
                    case .deleted:
                        docFlags.append(.deleted)
                    default:
                        break
                    }
                    
                    var error: TestServerError? = nil
                    
                    if let docError = doc.error as NSError? {
                        error = TestServerError(domain: .CBL, code: docError.code, message: docError.localizedDescription)
                    }
                    
                    self!.replicatorDocuments[replicatorID]?.append(
                        ContentTypes.DocumentReplication(
                            collection: "\(doc.scope).\(doc.collection)",
                            documentID: doc.id,
                            isPush: docChange.isPush,
                            flags: docFlags,
                            error: error)
                    )
                }
            })
        }
        
        replicator.start(reset: reset)
        
        Log.log(level: .debug, message: "Replicator started successfully with ID \(replicatorID)")
        
        return replicatorID
    }
    
    public func stopReplicator(forID replID: UUID) throws {
        Log.log(level: .debug, message: "Stop Replicator for ID \(replID) is requested.")
        guard let replicator = replicators[replID] else {
            throw TestServerError.badRequest("Replicator with ID '\(replID)' does not exist.")
        }
        replicator.stop()
        Log.log(level: .debug, message: "Stop Replicator for ID \(replID) is successfully requested.")
    }
    
    public func replicatorStatus(forID replID: UUID) -> ContentTypes.ReplicatorStatus? {
        Log.log(level: .debug, message: "Fetching Replicator status for ID \(replID)")
        guard let replicator = replicators[replID]
        else {
            Log.log(level: .debug, message: "Failed to fetch Replicator status, Replicator with ID \(replID) not found.")
            return nil
        }
        
        var activity: ContentTypes.ReplicatorActivity = .STOPPED
        
        switch replicator.status.activity {
        case .busy:
            activity = .BUSY
        case .connecting:
            activity = .CONNECTING
        case .idle:
            activity = .IDLE
        case .offline:
            activity = .OFFLINE
        case .stopped:
            activity = .STOPPED
        @unknown default:
            fatalError("Encountered unknown enum value from CBLReplicator.status.activity")
        }
        
        let progress = ContentTypes.ReplicatorStatus.Progress(completed: replicator.status.progress.completed == replicator.status.progress.total)
        
        var error: TestServerError? = nil
        if let replError = replicator.status.error as NSError? {
            error = TestServerError(domain: .CBL, code: replError.code, message: replError.localizedDescription)
        }
        
        var documents: [ContentTypes.DocumentReplication]? = nil
        
        if let replicatedDocuments = replicatorDocuments[replID] {
            documents = replicatedDocuments
            // Clear documents that have already been returned, per spec
            replicatorDocuments[replID] = []
        }
        
        let status = ContentTypes.ReplicatorStatus(activity: activity, progress: progress, documents: documents, error: error)
        
        Log.log(level: .debug, message: "Succeessfully fetched Replicator status for ID \(replID): \(status.description)")
        
        return status
    }
    
    public func collection(_ name: String, inDB dbName: String) throws -> Collection? {
        Log.log(level: .debug, message: "Fetching collecting '\(name)' in database '\(dbName)'")
        
        guard let database = databases[dbName]
        else {
            Log.log(level: .error, message: "Failed to fetch collection, database '\(dbName)' not open.")
            throw TestServerError.cblDBNotOpen
        }
        
        return try collection(name, inDB: database)
    }
    
    public func collection(_ name: String, inDB database: Database) throws -> Collection? {
        Log.log(level: .debug, message: "Fetching collection with DB: \(database.name), collection: \(name)")
        do {
            let spec = try CollectionSpec(name)
            let collection = try database.collection(name: spec.collection, scope: spec.scope)
            Log.log(level: .debug, message: "Fetched collection, result: \(collection.debugDescription)")
            return collection
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to fetch collection due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func getDocument(_ id: String, fromCollection collName: String, inDB dbName: String) throws -> Document? {
        Log.log(level: .debug, message: "Getting document '\(id)' from collection '\(collName)' in database '\(dbName)'")
        
        guard let collection = try collection(collName, inDB: dbName) else {
            throw TestServerError.badRequest("Cannot find collection '\(collName)' in db '\(dbName)'")
        }
        
        return try collection.document(id: id)
    }
    
    // Returns [scope_name.collection_name]
    public func getQualifiedCollections(fromDB dbName: String) throws -> Array<String> {
        Log.log(level: .debug, message: "Fetching all collection names from DB '\(dbName)'")
        
        guard let database = databases[dbName]
        else {
            Log.log(level: .error, message: "Failed to fetch collections, DB \(dbName) not open")
            throw TestServerError.cblDBNotOpen
        }
        
        do {
            var result: [String] = []
            for scope in try database.scopes() {
                for collection in try scope.collections() {
                    result.append("\(scope.name).\(collection.name)")
                }
            }
            Log.log(level: .debug, message: "Fetched all collections: \(result)")
            return result
            
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to fetch collections due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func performMaintenance(type: MaintenanceType, onDB dbName: String) throws {
        guard let db = databases[dbName]
        else { throw TestServerError.cblDBNotOpen }
        
        do {
            try db.performMaintenance(type: type)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func closeDatabase(withName dbName: String) throws {
        Log.log(level: .debug, message: "Closing database '\(dbName)'")
        guard let database = databases[dbName]
        else {
            Log.log(level: .debug, message: "Database \(dbName) was already closed.")
            return
        }
        
        do {
            try database.close()
            databases.removeValue(forKey: dbName)
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to close database due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
        
        Log.log(level: .debug, message: "Database '\(dbName)' closed successfully.")
    }
    
    public func createDatabase(dbName: String, dataset: String) throws {
        Log.log(level: .debug, message: "Create Database \(dbName) with dataset \(dataset)")
        
        // Load database with the dataset
        try loadDataset(withName: dataset, dbName: dbName)
        
        // Open database
        do {
            databases[dbName] = try Database(name: dbName)
        } catch(let error as NSError) {
            Log.log(level: .error, message: "CBL Error while re-opening DB: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
        Log.log(level: .debug, message: "Database '\(dbName)' has been created with the dataset \(dataset).")
    }
    
    public func createDatabase(dbName: String, collections: [String] = []) throws {
        Log.log(level: .debug, message: "Create Database \(dbName) with collections \(collections)")
        
        // For any reasons if the database exists, delete it.
        if Database.exists(withName: dbName) {
            try Database.delete(withName: dbName)
        }
        
        // Open database
        do {
            let db = try Database(name: dbName)
            for collName in collections {
                let spec = try CollectionSpec(collName)
                try _ = db.createCollection(name: spec.collection, scope: spec.scope)
            }
            databases[dbName] = db
        } catch(let error as NSError) {
            Log.log(level: .error, message: "CBL Error while re-opening DB: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
        Log.log(level: .debug, message: "Database '\(dbName)' has been created with the collections \(collections).")
    }
    
    public func reset() throws {
        Log.log(level: .debug, message: "Resetting all databases")
        for dbName in databases.keys {
            try closeDatabase(withName: dbName)
            try? Database.delete(withName: dbName)
        }
        databases.removeAll()
    }
    
    private static func getCBLAuthenticator(from auth: ReplicatorAuthenticator) throws -> Authenticator {
        switch auth {
        case let auth as ContentTypes.ReplicatorBasicAuthenticator:
            return BasicAuthenticator(username: auth.username, password: auth.password)
        case let auth as ContentTypes.ReplicatorSessionAuthenticator:
            return SessionAuthenticator(sessionID: auth.sessionID, cookieName: auth.cookieName)
        default:
            throw TestServerError.badRequest("'authenticator' parameter did not match a valid authenticator.")
        }
    }
    
    private static func getCBLReplicationFilter(from filter: ContentTypes.ReplicationFilter) throws -> ReplicationFilter {
        return try ReplicationFilterFactory.getFilter(withName: filter.name, params: filter.params)
    }
    
    private static func getCBLReplicationConflictResolver(from resolver: ContentTypes.ReplicationConflictResolver) throws -> ConflictResolverProtocol {
        return try ReplicationConflictResolverFactory.getResolver(withName: resolver.name, params: resolver.params)
    }
    
    private func loadDataset(withName name: String, dbName: String) throws {
        Log.log(level: .debug, message: "Loading dataset '\(name)' into DB '\(dbName)'")
        
        let datasetRelativePath = URL(fileURLWithPath: "dbs")
            .appendingPathComponent(datasetVersion)
            .appendingPathComponent("\(name).cblite2.zip")
            .relativePath
            
        let datasetZipURL = try downloadDatasetFileIfNecessary(relativePath: datasetRelativePath)
        Log.log(level: .debug, message: "Load dataset at \(datasetZipURL.path)")
        
        let fm = FileManager()
        
        let extractedDatasetDir = URL(filePath: databaseDirectory)
            .appendingPathComponent(kDatasetExtractedDirectory)
        
        let extractedDatasetPath = extractedDatasetDir
            .appendingPathComponent(datasetZipURL.deletingPathExtension().lastPathComponent)
            .path
        
        if(!fm.fileExists(atPath: extractedDatasetPath)) {
            Log.log(level: .debug, message: "Unzipping dataset \(datasetZipURL.lastPathComponent)")
            guard SSZipArchive.unzipFile(atPath: datasetZipURL.path, toDestination: extractedDatasetDir.path) else {
                Log.log(level: .error, message: "Error while unzipping dataset at \(datasetZipURL.absoluteString)")
                throw TestServerError(domain: .CBL, code: CBLError.cantOpenFile, message: "Couldn't unzip dataset archive.")
            }
        }
        
        // For any reasons if the database exists, delete it.
        if Database.exists(withName: dbName) {
            try Database.delete(withName: dbName)
        }
        
        do {
            Log.log(level: .debug, message: "Attempting to copy dataset from \(extractedDatasetPath)")
            try Database.copy(fromPath: extractedDatasetPath, toDatabase: dbName, withConfig: nil)
            Log.log(level: .debug, message: "Dataset '\(name)' successfully copied to DB '\(dbName)'")
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to copy dataset due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    private func datasetRelativePath(for name: String, version: String) -> String {
        return "dbs/\(version)/\(name).cblite2.zip"
    }
    
    private func downloadDatasetFileIfNecessary(relativePath: String) throws -> URL {
        let datasetPath = URL(filePath: databaseDirectory)
            .appendingPathComponent(kDatasetDownloadDirectory)
            .appendingPathComponent(relativePath)
        
        let fm = FileManager.default
        
        if (fm.fileExists(atPath: datasetPath.path)) {
            Log.log(level: .debug, message: "Skipping download, dataset already exists at pat \(datasetPath.path)")
            return datasetPath
        }
        
        let parentDir = datasetPath.deletingLastPathComponent()
        if (!fm.fileExists(atPath: parentDir.path)) {
            try fm.createDirectory(at: parentDir, withIntermediateDirectories: true)
        }
        
        guard let url = URL(string: relativePath, relativeTo: URL(string: kDatasetBaseURL)) else {
            throw TestServerError.badRequest("Invalid dataset path : \(relativePath)")
        }
        
        Log.log(level: .info, message: "Downloading dataset from \(url.absoluteString)")
        try FileDownloader.download(url: url, to: datasetPath.path)
        
        return datasetPath
    }
    
    public func loadBlob(filename: String) throws -> Blob {
        let blobRelativePath = URL(fileURLWithPath: "blobs")
            .appendingPathComponent(filename)
            .relativePath
        
        let blobFileURL = try downloadDatasetFileIfNecessary(relativePath: blobRelativePath)
        Log.log(level: .debug, message: "Load blob from \(blobFileURL.path)")
        
        let contentType: String = {
            switch blobFileURL.pathExtension {
            case "jpeg", "jpg": return "image/jpeg"
            default: return "application/octet-stream"
            }
        }()
        
        do {
            return try Blob(contentType: contentType, fileURL: blobFileURL)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func blobFileExists(forBlob blob: Blob, inDB dbName: String) throws -> Bool {
        guard let db = databases[dbName]
        else { throw TestServerError.cblDBNotOpen }
        
        do {
            return try db.getBlob(properties: blob.properties) != nil
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
}
	
