//
//  DatabaseManager.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import CouchbaseLiteSwift
import ZipArchive
import CryptoKit

class DatabaseManager {
    private var databases : [ String : Database ] = [:]
    
    private var replicators : [ UUID : Replicator ] = [:]
    private var replicatorDocuments : [ UUID : [ ContentTypes.DocumentReplication ] ] = [:]
    private var replicatorDocumentsToken : [ UUID : ListenerToken ] = [:]
    
    private var multipeerReplicators : [ UUID : MultipeerReplicator ] = [:]
    private var peerReplicatorStatus : [ UUID : [ PeerID: Replicator.Status ] ] = [:]
    private var peerReplicatorStatusToken : [ UUID : ListenerToken ] = [:]
    private var peerReplicatorDocuments : [ UUID : [ PeerID: [ ContentTypes.DocumentReplication ] ] ] = [:]
    private var peerReplicatorDocumentsToken : [ UUID : ListenerToken ] = [:]
    
    private let listenerQueue = DispatchQueue(label: "DatabaseManagerListenerQueue")
    
    public init() { }
    
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
                    collConfig.pullFilter = try DatabaseManager.getCBLReplicationFilter(from: pullFilter).toReplicationFilter()
                }
                if let pushFilter = configColl.pushFilter {
                    collConfig.pushFilter = try DatabaseManager.getCBLReplicationFilter(from: pushFilter).toReplicationFilter()
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
            
            let listenerToken = replicator.addDocumentReplicationListener(withQueue: listenerQueue) { [weak self] docChange in
                guard let strongSelf = self else { return }
                
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
                    
                    strongSelf.replicatorDocuments[replicatorID]?.append(
                        ContentTypes.DocumentReplication(
                            collection: "\(doc.scope).\(doc.collection)",
                            documentID: doc.id,
                            isPush: docChange.isPush,
                            flags: docFlags,
                            error: error)
                    )
                }
            }
            
            replicatorDocumentsToken[replicatorID] = listenerToken
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
        
        var status: ContentTypes.ReplicatorStatus?
        
        listenerQueue.sync {
            guard let replicator = replicators[replID] else {
                Log.log(level: .debug, message: "Failed to fetch Replicator status, Replicator with ID \(replID) not found.")
                return
            }
            
            var docs: [ContentTypes.DocumentReplication] = replicatorDocuments[replID] ?? []
            
            replicatorDocuments[replID] = [] // Reset after return per spec
            
            status = ContentTypes.ReplicatorStatus(status: replicator.status, docs: docs)
            Log.log(level: .debug, message: "Succeessfully fetched Replicator status for ID \(replID): \(status!.description)")
        }
        
        return status
    }
    
    public func startMultipeerReplicator(config: ContentTypes.MultipeerReplicatorConfiguration) throws -> UUID {
        Log.log(level: .debug, message: "Starting Multipeer Replicator")
        
        let identity = try DatabaseManager.multipeerReplicatorIdentity(for: config)
        
        let authenticator = try DatabaseManager.multipeerAuthenticator(for: config.authenticator)
        
        var collectionConfigs: [MultipeerCollectionConfiguration] = []
        for replColl in config.collections {
            for name in replColl.names {
                guard let collection = try self.collection(name, inDB: config.database) else {
                    Log.log(level: .error, message: "Failed to start Multipeer Replicator as collection '\(name)' does not exist in \(config.database).")
                    throw TestServerError.badRequest("Collection '\(name)' does not exist in \(config.database).")
                }
                
                var collConfig = MultipeerCollectionConfiguration(collection: collection)
                
                collConfig.documentIDs = replColl.documentIDs
                
                if let pullFilter = replColl.pullFilter {
                    collConfig.pullFilter = try DatabaseManager.getCBLReplicationFilter(from: pullFilter).toMultipeerReplicationFilter()
                }
                if let pushFilter = replColl.pushFilter {
                    collConfig.pushFilter = try DatabaseManager.getCBLReplicationFilter(from: pushFilter).toMultipeerReplicationFilter()
                }
                if let resolver = replColl.conflictResolver {
                    collConfig.conflictResolver = try DatabaseManager.getCBLReplicationConflictResolver(from: resolver)
                }
                
                collectionConfigs.append(collConfig)
            }
        }
        
        let conf = MultipeerReplicatorConfiguration(
            peerGroupID: config.peerGroupID,
            identity: identity,
            authenticator: authenticator,
            collections: collectionConfigs)
        
        let id = UUID()
        
        let multipeerReplicator = try MultipeerReplicator(config: conf)
        
        let listenerToken = multipeerReplicator.addPeerReplicatorStatusListener(on: listenerQueue) { [weak self] status in
            guard let strongSelf = self else { return }
            strongSelf.peerReplicatorStatus[id, default: [:]][status.peerID] = status.status
        }
        
        let docReplToken = multipeerReplicator.addPeerDocumentReplicationListener(on: listenerQueue) { [weak self] docRepl in
            guard let strongSelf = self else { return }
            var docs: [ContentTypes.DocumentReplication] = []
            docRepl.documents.forEach { doc in
                docs.append(ContentTypes.DocumentReplication.init(doc: doc, isPush: !docRepl.incoming))
            }
            strongSelf.peerReplicatorDocuments[id, default: [:]][docRepl.peerID, default: []] += docs
        }
        
        multipeerReplicator.start()
        
        multipeerReplicators[id] = multipeerReplicator
        peerReplicatorStatusToken[id] = listenerToken
        peerReplicatorDocumentsToken[id] = docReplToken
        
        return id
    }
    
    public func stopMultipeerReplicator(forID id: UUID) throws {
        Log.log(level: .debug, message: "Stop Multipeer Replicator for ID \(id) is requested.")
        guard let replicator = multipeerReplicators[id] else {
            throw TestServerError.badRequest("Multipeer Replicator ID'\(id)' does not exist.")
        }
        replicator.stop()
        Log.log(level: .debug, message: "Stop Multipeer Replicator for ID \(id) is successfully requested.")
    }
    
    public func multipeerReplicatorStatus(forID id: UUID) -> ContentTypes.MultipeerReplicatorStatus? {
        Log.log(level: .debug, message: "Getting MultipeerReplicator Status for ID \(id)")
        
        var status: ContentTypes.MultipeerReplicatorStatus?
        
        listenerQueue.sync {
            guard let repl = multipeerReplicators[id] else {
                Log.log(level: .debug, message: "Failed to get MultipeerReplicator Status, MultipeerReplicator with ID \(id) not found.")
                return
            }
            
            var replicators: [ContentTypes.PeerReplicatorStatus] = []
            
            if let statuses = peerReplicatorStatus[id] {
                statuses.forEach { peerID, status in
                    let docs = peerReplicatorDocuments[id]?[peerID] ?? []
                    let replStatus = ContentTypes.ReplicatorStatus.init(status: status, docs: docs)
                    replicators.append(ContentTypes.PeerReplicatorStatus(peerID: "\(peerID)", status: replStatus))
                    peerReplicatorDocuments[id]?[peerID] = [] // Reset after return per spec
                }
            }
            
            status = ContentTypes.MultipeerReplicatorStatus.init(replicators: replicators)
        }
        
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
        
        // For the first time called, reset the temp directory for extracting the dataset
        if databases.isEmpty {
            try DatabaseManager.resetExtractedDatasetDir()
        }
        
        // Load database with the dataset
        try DatabaseManager.loadDataset(withName: dataset, dbName: dbName)
        
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
        
        // For the first time called, reset the temp directory for extracting the dataset
        if databases.isEmpty {
            try DatabaseManager.resetExtractedDatasetDir()
        }
        
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
        
        // Reset all replicators:
        replicators.removeAll()
        replicatorDocuments.removeAll()
        replicatorDocumentsToken.removeAll()
        
        // Reset all multipeer replicators:
        multipeerReplicators.values.forEach { $0.stop() } // Temporary until all close database also stops multipeer replicator
        multipeerReplicators.removeAll()
        
        peerReplicatorStatus.removeAll()
        peerReplicatorStatusToken.removeAll()
        
        peerReplicatorDocuments.removeAll()
        peerReplicatorDocumentsToken.removeAll()
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
    
    private static func getCBLReplicationFilter(from filter: ContentTypes.ReplicationFilter) throws -> AnyReplicationFilter {
        return try ReplicationFilterFactory.getFilter(withName: filter.name, params: filter.params)
    }
    
    private static func getCBLReplicationConflictResolver(from resolver: ContentTypes.ReplicationConflictResolver) throws -> ConflictResolver {
        return try ReplicationConflictResolverFactory.getResolver(withName: resolver.name, params: resolver.params)
    }
    
    private static func loadDataset(withName name: String, dbName: String) throws {
        Log.log(level: .debug, message: "Loading dataset '\(name)' into DB '\(dbName)'")
        
        let res = ("dbs" as NSString).appendingPathComponent(name)
        guard let datasetZipURL = Bundle.main.url(forResource: res, withExtension: "cblite2.zip") else {
            Log.log(level: .error, message: "Failed to load dataset, dataset '\(name)' does not exist.")
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "Dataset does not exist")
        }
        Log.log(level: .debug, message: "Found dataset at \(datasetZipURL.absoluteString)")
        
        // datasetZipURL is "../x.cblite2.zip", datasetURL is "../x.cblite2"
        let fm = FileManager()
        
        // If the dataset has not been unzipped previously
        let extDir = DatabaseManager.extractedDatasetDir()
        let dbFileName = datasetZipURL.deletingPathExtension().lastPathComponent
        let extDatasetPath = (extDir as NSString).appendingPathComponent(dbFileName)
        if(!fm.fileExists(atPath: extDatasetPath)) {
            Log.log(level: .debug, message: "Unzipping dataset \(datasetZipURL.lastPathComponent)")
            // Unzip dataset archive
            guard SSZipArchive.unzipFile(atPath: datasetZipURL.relativePath, toDestination: extDir)
            else {
                Log.log(level: .error, message: "Error while unzipping dataset at \(datasetZipURL.absoluteString)")
                throw TestServerError(domain: .CBL, code: CBLError.cantOpenFile, message: "Couldn't unzip dataset archive.")
            }
        }
        
        // For any reasons if the database exists, delete it.
        if Database.exists(withName: dbName) {
            try Database.delete(withName: dbName)
        }
        
        do {
            Log.log(level: .debug, message: "Attempting to copy dataset from \(extDatasetPath)")
            try Database.copy(fromPath: extDatasetPath, toDatabase: dbName, withConfig: nil)
            Log.log(level: .debug, message: "Dataset '\(name)' successfully copied to DB '\(dbName)'")
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to copy dataset due to CBL error: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    private static func extractedDatasetDir() -> String {
        return (NSTemporaryDirectory() as NSString).appendingPathComponent("TestServer-iOS-Dataset");
    }
    
    private static func resetExtractedDatasetDir() throws {
        let dir = extractedDatasetDir()
        if FileManager.default.fileExists(atPath: dir) {
            try! FileManager.default.removeItem(atPath: dir)
        }
        
        do {
            try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        } catch(let error as NSError) {
            Log.log(level: .error, message: "Failed to create temp directory for extracting dataset zip files: \(error)")
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    private static func multipeerReplicatorIdentity(for config: ContentTypes.MultipeerReplicatorConfiguration) throws -> TLSIdentity {
        let label = "ios-multipeer-\(config.peerGroupID)"
        
        guard let data = Data(base64Encoded: config.identity.data) else {
            throw TestServerError.badRequest("Invalid multipeer replictor's identity data")
        }
        
        try TLSIdentity.deleteIdentity(withLabel: label)
        return try TLSIdentity.importIdentity(withData: data, password: config.identity.password, label: label)
    }
    
    private static func multipeerAuthenticator(for config: ContentTypes.MultipeerReplicatorCAAuthenticator?) throws -> MultipeerCertificateAuthenticator {
        guard let auth = config else {
            return MultipeerCertificateAuthenticator { peer, certs in
                return true
            }
        }
        
        var lines = auth.certificate
            .components(separatedBy: .newlines)
            .filter { !$0.contains("-----BEGIN CERTIFICATE-----") &&
                      !$0.contains("-----END CERTIFICATE-----") &&
                      !$0.isEmpty }
        
        let certData = lines.joined()

        guard let derData = Data(base64Encoded: certData) else {
            throw TestServerError.badRequest("Failed to convert multipeer authenticator's root certificate from PEM to DER")
        }
        
        guard let rootCert = SecCertificateCreateWithData(nil, derData as CFData) else {
            throw TestServerError.badRequest("Invalid multipeer authenticator's root certificate")
        }
        
        return MultipeerCertificateAuthenticator(rootCerts: [rootCert])
    }
}
