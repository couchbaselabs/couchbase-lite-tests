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
    
    private init() {
        Database.log.console.domains = .all
        Database.log.console.level = .verbose
    }
    
    @discardableResult
    public func addCollection(dbName: String, scope: String, name: String) throws -> Collection {
        guard let database = databases[dbName]
        else { throw TestServerError.cblDBNotOpen }
        
        do {
            return try database.createCollection(name: name, scope: scope)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func runQuery(dbName: String, queryString: String) throws -> ResultSet {
        guard let database = databases[dbName]
        else {
            throw TestServerError.cblDBNotOpen
        }
        
        do {
            let query = try database.createQuery(queryString)
            return try query.execute()
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func startReplicator(config: ContentTypes.ReplicatorConfiguration, reset: Bool) throws -> UUID {
        guard let database = databases[config.database]
        else { throw TestServerError.cblDBNotOpen }
        
        guard let endpointURL = URL(string: config.endpoint)
        else { throw TestServerError.badRequest }
        
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
                else { throw TestServerError.badRequest }
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
        
        return replicatorID
    }
    
    public func replicatorStatus(forID replID: UUID) -> ContentTypes.ReplicatorStatus? {
        guard let replicator = replicators[replID]
        else { return nil }
        
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
        
        return ContentTypes.ReplicatorStatus(activity: activity, progress: progress, documents: documents, error: error)
    }
    
    public func collection(_ name: String, inDB dbName: String) throws -> Collection? {
        guard let database = databases[dbName]
        else { throw TestServerError.cblDBNotOpen }
        
        return try collection(name, inDB: database)
    }
    
    public func collection(_ name: String, inDB database: Database) throws -> Collection? {
        let scopeAndColl = name.components(separatedBy: ".")
        guard let scope = scopeAndColl.first, let coll = scopeAndColl.last
        else { throw TestServerError.badRequest }
        
        do {
            return try database.collection(name: coll, scope: scope)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    // Returns [scope_name.collection_name]
    public func getQualifiedCollections(fromDB dbName: String) throws -> Array<String> {
        guard let database = databases[dbName]
        else { throw TestServerError.cblDBNotOpen }
        
        do {
            var result: [String] = []
            for scope in try database.scopes() {
                for collection in try scope.collections() {
                    result.append("\(scope.name).\(collection.name)")
                }
            }
            return result
            
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func closeDatabase(withName dbName: String) throws {
        guard let database = databases[dbName]
        else { return }
        
        do {
            try database.close()
            databases.removeValue(forKey: dbName)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    public func reset(dbName: String, dataset: String? = nil) throws {
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
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
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
            throw TestServerError.badRequest
        }
    }
    
    private static func getCBLReplicationFilter(from filter: ContentTypes.ReplicationFilter) throws -> ReplicationFilter {
        return try ReplicationFilterFactory.getFilter(withName: filter.name, params: filter.params)
    }
    
    private static func loadDataset(withName name: String, dbName: String) throws {
        guard let datasetZipURL = Bundle.main.url(forResource: name, withExtension: "cblite2.zip")
        else { throw TestServerError(domain: .TESTSERVER, code: 400, message: "Dataset does not exist") }
        
        // datasetZipURL is "../x.cblite2.zip", datasetURL is "../x.cblite2"
        let datasetURL = datasetZipURL.deletingPathExtension()
        let fm = FileManager()
        
        // If the dataset has not been unzipped previously
        if(!fm.fileExists(atPath: datasetURL.relativePath)) {
            // Unzip dataset archive
            guard SSZipArchive.unzipFile(atPath: datasetZipURL.relativePath,
                                         toDestination: datasetZipURL.deletingLastPathComponent().relativePath)
            else {
                throw TestServerError(domain: .CBL, code: CBLError.cantOpenFile, message: "Couldn't unzip dataset archive.")
            }
        }
        
        do {
            try Database.copy(fromPath: datasetURL.relativePath, toDatabase: dbName, withConfig: nil)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
}
