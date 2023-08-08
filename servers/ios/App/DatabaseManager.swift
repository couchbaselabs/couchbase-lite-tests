//
//  DatabaseManager.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import CouchbaseLiteSwift

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
        return try? database?.collection(name: name)
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
    
    public func reset() throws {
        guard let path = database?.path
        else { throw TestServerError.cblDBNotOpen }
        closeDatabase()
        
        do {
            let fm = FileManager()
            try fm.removeItem(atPath: path)
        } catch  {
            throw TestServerError(domain: .TESTSERVER, code: error._code, message: "Failed to delete database file")
        }
        
        do {
            database = try Database(name: self.dbName)
        } catch {
            throw TestServerError(domain: .CBL, code: CBLError.cantOpenFile, message: "Couldn't open database")
        }
        
    }
}
