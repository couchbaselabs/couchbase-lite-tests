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
    
    public func collection(_ name: String, inDB dbName: String) throws -> Collection? {
        guard let database = databases[dbName]
        else { throw TestServerError.cblDBNotOpen }
        
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
        if let database = databases[dbName] {
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
