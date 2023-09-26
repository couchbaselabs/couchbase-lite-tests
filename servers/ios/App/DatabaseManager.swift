//
//  DatabaseManager.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import CouchbaseLiteSwift
import ZipArchive

class DatabaseManager {    
    public static var shared : DatabaseManager?
    
    private var databases : [ String : Database ] = [:]
    private var replicators : [ UUID : Replicator ] = [:]
    private var replicatorDocuments : [ UUID : [ContentTypes.DocumentReplication] ] = [:]
    
    public static func InitializeShared() {
        if shared == nil {
            shared = DatabaseManager()
        }
    }
    
//    private init() {
//        Database.log.console.domains = .all
//        Database.log.console.level = .verbose
//    }
    
    @discardableResult
    public func addCollection(dbName: String, scope: String, name: String) throws -> Collection {
        TestServer.logger.log(level: .debug, "Creating collection: \(scope).\(name) in database: \(dbName)")
        guard let database = databases[dbName]
        else {
            TestServer.logger.log(level: .error, "Failed to create collection, database '\(dbName)' does not exist")
            throw TestServerError.cblDBNotOpen
        }
        
        do {
            let coll = try database.createCollection(name: name, scope: scope)
            TestServer.logger.log(level: .debug, "Collection \(scope).\(name) successfully created in database \(dbName)")
            return coll
        } catch(let error as NSError) {
            TestServer.logger.log(level: .error, "Failed to create collection due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func runQuery(dbName: String, queryString: String) throws -> ResultSet {
        TestServer.logger.log(level: .debug, "Running query: `\(queryString)` in database: \(dbName)")
        guard let database = databases[dbName]
        else {
            TestServer.logger.log(level: .error, "Failed to run query, database '\(dbName)' does not exist")
            throw TestServerError.cblDBNotOpen
        }
        
        do {
            let query = try database.createQuery(queryString)
            let result = try query.execute()
            TestServer.logger.log(level: .debug, "Query successfully executed.")
            return result
        } catch(let error as NSError) {
            TestServer.logger.log(level: .error, "Failed to run query due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func startReplicator(config: ContentTypes.ReplicatorConfiguration, reset: Bool) throws -> UUID {
        TestServer.logger.log(level: .debug, "Starting Replicator with config: \(config.description)")
        
        guard let database = databases[config.database]
        else {
            TestServer.logger.log(level: .error, "Failed to start Replicator, database '\(config.database)' does not exist")
            throw TestServerError.cblDBNotOpen
        }
        
        guard let endpointURL = URL(string: config.endpoint)
        else {
            TestServer.logger.log(level: .error, "Failed to start Replicator, invalid endpoint URL.")
            throw TestServerError.badRequest("Endpoint URL is not a valid URL.")
        }
        
        var replConfig = ReplicatorConfiguration(target: URLEndpoint(url: endpointURL))
        
        replConfig.authenticator = try DatabaseManager.getCBLAuthenticator(from: config.authenticator)
        
        switch(config.replicatorType) {
        case .push:
            replConfig.replicatorType = .push
        case .pull:
            replConfig.replicatorType = .pull
        case .pushpull:
            replConfig.replicatorType = .pushAndPull
        }
        
        replConfig.continuous = config.continuous
        
        for configColl in config.collections {
            let collections = try configColl.names.map({ collName in
                guard let collection = try collection(collName, inDB: database)
                else {
                    TestServer.logger.log(level: .error, "Failed to start Replicator, Collection '\(collName)' does not exist in \(config.database).")
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
            replConfig.addCollections(collections, config: collConfig)
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
        
        TestServer.logger.log(level: .debug, "Replicator started successfully with ID \(replicatorID)")
        
        return replicatorID
    }
    
    public func replicatorStatus(forID replID: UUID) -> ContentTypes.ReplicatorStatus? {
        TestServer.logger.log(level: .debug, "Fetching Replicator status for ID \(replID)")
        guard let replicator = replicators[replID]
        else {
            TestServer.logger.log(level: .debug, "Failed to fetch Replicator status, Replicator with ID \(replID) not found.")
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
        
        TestServer.logger.log(level: .debug, "Succeessfully fetched Replicator status for ID \(replID): \(status.description)")
        
        return status
    }
    
    public func collection(_ name: String, inDB dbName: String) throws -> Collection? {
        TestServer.logger.log(level: .debug, "Fetching collecting '\(name)' in database '\(dbName)'")
        
        guard let database = databases[dbName]
        else {
            TestServer.logger.log(level: .error, "Failed to fetch collection, database '\(dbName)' not open.")
            throw TestServerError.cblDBNotOpen
        }
        
        return try collection(name, inDB: database)
    }
    
    public func collection(_ name: String, inDB database: Database) throws -> Collection? {
        let scopeAndColl = name.components(separatedBy: ".")
        guard let scope = scopeAndColl.first, let coll = scopeAndColl.last
        else {
            TestServer.logger.log(level: .error, "Failed to fetch collection, '\(name)' is an invalid FQN.")
            throw TestServerError.badRequest("'\(name)' is not a valid qualified collection name.")
        }
        
        TestServer.logger.log(level: .debug, "Fetching collection with DB: \(database.name), scope: \(scope), collection: \(coll)")
        
        do {
            let collection = try database.collection(name: coll, scope: scope)
            TestServer.logger.log(level: .debug, "Fetched collection, result: \(collection.debugDescription)")
            return collection
        } catch(let error as NSError) {
            TestServer.logger.log(level: .error, "Failed to fetch collection due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    // Returns [scope_name.collection_name]
    public func getQualifiedCollections(fromDB dbName: String) throws -> Array<String> {
        TestServer.logger.log(level: .debug, "Fetching all collection names from DB '\(dbName)'")
        
        guard let database = databases[dbName]
        else {
            TestServer.logger.log(level: .error, "Failed to fetch collections, DB \(dbName) not open")
            throw TestServerError.cblDBNotOpen
        }
        
        do {
            var result: [String] = []
            for scope in try database.scopes() {
                for collection in try scope.collections() {
                    result.append("\(scope.name).\(collection.name)")
                }
            }
            TestServer.logger.log(level: .debug, "Fetched all collections: \(result)")
            return result
            
        } catch(let error as NSError) {
            TestServer.logger.log(level: .error, "Failed to fetch collections due to CBL error: \(error)")
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
    
    public func blobFileExists(forBlob blob: Blob, inDB dbName: String) throws -> Bool {
        guard let db = databases[dbName]
        else { throw TestServerError.cblDBNotOpen }
        
        do {
            return try db.getBlob(properties: blob.properties) != nil
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func closeDatabase(withName dbName: String) throws {
        TestServer.logger.log(level: .debug, "Closing database '\(dbName)'")
        guard let database = databases[dbName]
        else {
            TestServer.logger.log(level: .debug, "Database \(dbName) was already closed.")
            return
        }
        
        do {
            try database.close()
            databases.removeValue(forKey: dbName)
        } catch(let error as NSError) {
            TestServer.logger.log(level: .error, "Failed to close database due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
        
        TestServer.logger.log(level: .debug, "Database '\(dbName)' closed successfully.")
    }
    
    public func reset(dbName: String, dataset: String? = nil) throws {
        TestServer.logger.log(level: .debug, "Resetting DB \(dbName)\(dataset != nil ? " with dataset \(dataset!)" : "")")
        // If database is open, close
        if databases[dbName] != nil {
            try closeDatabase(withName: dbName)
        }
        
        // Delete any existing DB with this name
        try? Database.delete(withName: dbName)
        
        // Load dataset if requested (performs Database.copy)
        if let dataset = dataset {
            try DatabaseManager.loadDataset(withName: dataset, dbName: dbName)
        }
        
        // Open database
        do {
            databases[dbName] = try Database(name: dbName)
        } catch(let error as NSError) {
            TestServer.logger.log(level: .error, "CBL Error while re-opening DB: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
        TestServer.logger.log(level: .debug, "Database '\(dbName)' has been reset.")
    }
    
    public func resetAll() throws {
        for dbName in databases.keys {
            try reset(dbName: dbName)
        }
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
    
    private static func loadDataset(withName name: String, dbName: String) throws {
        TestServer.logger.log(level: .debug, "Loading dataset '\(name)' into DB '\(dbName)'")
        
        guard let datasetZipURL = Bundle.main.url(forResource: name, withExtension: "cblite2.zip")
        else {
            TestServer.logger.log(level: .error, "Failed to load dataset, dataset '\(name)' does not exist.")
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "Dataset does not exist")
        }
        
        TestServer.logger.log(level: .debug, "Found dataset at \(datasetZipURL.absoluteString)")
        
        // datasetZipURL is "../x.cblite2.zip", datasetURL is "../x.cblite2"
        let datasetURL = datasetZipURL.deletingPathExtension()
        let fm = FileManager()
        
        // If the dataset has not been unzipped previously
        if(!fm.fileExists(atPath: datasetURL.relativePath)) {
            TestServer.logger.log(level: .debug, "Unzipping dataset \(datasetZipURL.lastPathComponent)")
            // Unzip dataset archive
            guard SSZipArchive.unzipFile(atPath: datasetZipURL.relativePath,
                                         toDestination: datasetZipURL.deletingLastPathComponent().relativePath)
            else {
                TestServer.logger.log(level: .error, "Error while unzipping dataset at \(datasetZipURL.absoluteString)")
                throw TestServerError(domain: .CBL, code: CBLError.cantOpenFile, message: "Couldn't unzip dataset archive.")
            }
        }
        
        do {
            TestServer.logger.log(level: .debug, "Attempting to copy dataset from \(datasetURL.relativePath)")
            try Database.copy(fromPath: datasetURL.relativePath, toDatabase: dbName, withConfig: nil)
            TestServer.logger.log(level: .debug, "Dataset '\(name)' successfully copied to DB '\(dbName)'")
        } catch(let error as NSError) {
            TestServer.logger.log(level: .error, "Failed to copy dataset due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
}
