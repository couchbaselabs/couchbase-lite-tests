//
//  DatabaseManager.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import CouchbaseLiteSwift
import ZipArchive

class DatabaseManager {    
    static var shared : DatabaseManager?
    
    private let dbName: String
    private var database : Database?
    
    public static func InitializeShared(databaseName dbName: String = "cbltests") {
        shared = DatabaseManager(dbName: dbName)
    }
    
    private init(dbName: String = "cbltests") {
        Database.log.console.domains = .all
        Database.log.console.level = .verbose
        
        self.dbName = dbName
        do {
            database = try Database(name: dbName)
        } catch {
            fatalError(error.localizedDescription)
        }
        
        if(DatabaseManager.shared == nil) {
            DatabaseManager.shared = self
        }
    }
    
    public func addCollection(scope: String, name: String) -> Collection? {
        return try? database?.createCollection(name: name, scope: scope)
    }
    
    public func getDatabaseName() -> String {
        if let dbname = database?.name {
            return dbname
        }
        return ""
    }
    
    public func createQuery(queryString: String) -> Query? {
        return try? database?.createQuery(queryString)
    }
    
    public func collections() -> [Collection]? {
        return try? database?.collections()
    }
    
    public func collection(_ name: String) -> Collection? {
        let scopeAndColl = name.components(separatedBy: ".")
        guard let scope = scopeAndColl.first, let coll = scopeAndColl.last
        else { return nil }
        return try? database?.collection(name: coll, scope: scope)
    }
    
    // Returns [scope_name.collection_name]
    public func getCollectionNamesWithScope() -> Array<String> {
        if let collections = try? database?.collections() {
            return collections.map({ coll in "\(coll.scope.name).\(coll.name)" })
        }
        return []
    }
    
    public func closeDatabase() {
        do {
            try database?.close()
            database = nil
        } catch {
            fatalError(error.localizedDescription)
        }
    }
    
    public func reset(dataset: String? = nil) throws {
        guard let path = database?.path,
              let config = database?.config,
              let name = database?.name
        else { throw TestServerError.cblDBNotOpen }
        closeDatabase()
        
        do {
            let fm = FileManager()
            try fm.removeItem(atPath: path)
        } catch  {
            throw TestServerError(domain: .TESTSERVER, code: 500, message: "Failed to delete database file.")
        }
        
        if let dataset = dataset {
            // TODO: Multiple DBs, use db name param from request
            try DatabaseManager.loadDataset(withName: dataset, dbName: name, dbConfig: config)
        }
        
        do {
            database = try Database(name: name)
        } catch {
            throw TestServerError(domain: .CBL, code: CBLError.cantOpenFile, message: "Couldn't open database.")
        }
    }
    
    private static func loadDataset(withName name: String, dbName: String, dbConfig: DatabaseConfiguration) throws {
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
            try Database.copy(fromPath: datasetURL.relativePath, toDatabase: dbName, withConfig: dbConfig)
        } catch {
            throw TestServerError(domain: .CBL, code: CBLError.cantOpenFile, message: "Couldn't copy dataset to database.")
        }
    }
}
