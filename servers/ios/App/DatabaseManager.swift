//
//  DatabaseManager.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import CouchbaseLiteSwift

class DatabaseManager {
    let dbName: String
    var database : Database?
    
    init(dbName: String = "cbltests") {
        
        Database.log.console.domains = .all
        Database.log.console.level = .verbose
        
        self.dbName = dbName
        do {
            database = try Database(name: dbName)
        } catch {
            fatalError(error.localizedDescription)
        }
    }
    
    public func addCollection(scope: String, name: String) -> Collection? {
        return try? database?.createCollection(name: name, scope: scope)
    }
    
    public func closeDatabase() {
        do {
            try database?.close()
            database = nil
        } catch {
            fatalError(error.localizedDescription)
        }
    }
    
    public func reset() {
        guard let path = database?.path
        else { fatalError("Could not get database's path!") }
        closeDatabase()
        
        do {
            let fm = FileManager()
            try fm.removeItem(atPath: path)
        } catch {
            fatalError(error.localizedDescription)
        }
        
        do {
            database = try Database(name: self.dbName)
        } catch {
            fatalError(error.localizedDescription)
        }
        
    }
}
