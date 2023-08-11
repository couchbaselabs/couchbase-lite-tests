//
//  DocumentSnapshot.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import CouchbaseLiteSwift

typealias Snapshot = Dictionary<String, Document?>

extension Snapshot {
    static var currentSnapshots: [ UUID : Snapshot ] = [:]
    
    static func saveSnapshot(dbName: String, docIDs: [ContentTypes.DocumentID]) throws -> UUID {
        guard let dbManager = DatabaseManager.shared
        else { throw TestServerError.cblDBNotOpen }
        var newSnapshot = Snapshot()
        for docID in docIDs {
            guard let collection = try dbManager.collection(docID.collection, inDB: dbName)
            else { throw TestServerError.badRequest }
            
            do {
                let doc = try collection.document(id: docID.id)
                newSnapshot["\(collection.scope.name).\(collection.name).\(docID.id)"] = doc
            } catch(let error as NSError) {
                throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
            }
        }
        
        let snapID = UUID()
        currentSnapshots[snapID] = newSnapshot
        return snapID
    }
    
    static func verifyChanges(dbName: String, snapshotID: String, changes: [ContentTypes.DatabaseUpdateItem]) throws -> ContentTypes.VerifyResponse {
        guard let uuid = UUID(uuidString: snapshotID),
              let snapshot = currentSnapshots[uuid]
        else { throw TestServerError.badRequest }
        
        guard let dbManager = DatabaseManager.shared
        else { throw TestServerError.cblDBNotOpen }
        
        for change in changes {
            let snapshotKey = "\(change.collection).\(change.documentID)"
            
            guard snapshot.keys.contains(snapshotKey)
            else { throw TestServerError.badRequest }
            
            guard let collection = try dbManager.collection(change.collection, inDB: dbName)
            else { throw TestServerError.badRequest }
            
            var existingDoc: Document? = nil
            
            do {
                existingDoc = try collection.document(id: change.documentID)
            } catch(let error as NSError) {
                throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
            }
            
            if(change.type == .PURGE || change.type == .DELETE) {
                if(existingDoc != nil) {
                    return ContentTypes.VerifyResponse(result: false, description: "Deleted or purged document \(snapshotKey) still exists!")
                }
                continue
            }
            
            if(existingDoc == nil) {
                return ContentTypes.VerifyResponse(result: false, description: "Document \(snapshotKey) not found to verify!")
            }
            
            // We can force-unwrap here because we earlier checked that snapshot has snapshotKey
            let snapshotDoc = snapshot[snapshotKey]!
            let mutableSnapshotDoc = snapshotDoc?.toMutable() ?? MutableDocument(id: change.documentID)
            
            try DocumentUpdater.update(doc: mutableSnapshotDoc, updatedProperties: change.updatedProperties, removedProperties: change.removedProperties)
            
            let compareResult = try DocComparison.isEqual(mutableSnapshotDoc, existingDoc!)
            if(!compareResult.success) {
                return ContentTypes.VerifyResponse(result: false, description: "Contents for document \(snapshotKey) did not match!", expected: compareResult.expected, actual: compareResult.actual)
            }
        }
        
        return ContentTypes.VerifyResponse(result: true, description: "Successfully verified changes.")
    }
}
