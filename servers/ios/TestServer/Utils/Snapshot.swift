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
            else { throw TestServerError.badRequest("Cannot find collection '\(docID.collection)' in db '\(dbName)'") }
            
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
        else { throw TestServerError.badRequest("Snapshot with ID '\(snapshotID)' does not exist.") }
        
        guard let dbManager = DatabaseManager.shared
        else { throw TestServerError.cblDBNotOpen }
        
        for change in changes {
            let snapshotKey = "\(change.collection).\(change.documentID)"
            
            guard snapshot.keys.contains(snapshotKey)
            else { throw TestServerError.badRequest("Snapshot '\(snapshotID)' does not contain key '\(change.collection).\(change.documentID)'") }
            
            guard let collection = try dbManager.collection(change.collection, inDB: dbName)
            else { throw TestServerError.badRequest("Cannot find collection '\(change.collection)' in db '\(dbName)'") }
            
            var existingDoc: Document? = nil
            
            do {
                existingDoc = try collection.document(id: change.documentID)
            } catch(let error as NSError) {
                throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
            }
            
            if(change.type == .DELETE) {
                if(existingDoc != nil) {
                    return ContentTypes.VerifyResponse(result: false, description: DocComparison.FailDescriptions.case2(docID: change.documentID, qualifiedCollection: change.collection))
                }
                continue
            } else if(change.type == .PURGE) {
                if(existingDoc != nil) {
                    return ContentTypes.VerifyResponse(result: false, description: DocComparison.FailDescriptions.case3(docID: change.documentID, qualifiedCollection: change.collection))
                }
                continue
            }
            
            guard let existingDoc = existingDoc
            else {
                return ContentTypes.VerifyResponse(result: false, description: DocComparison.FailDescriptions.case1(docID: change.documentID, qualifiedCollection: change.collection))
            }
            
            // We can force-unwrap here because we earlier checked that snapshot has snapshotKey
            guard let snapshotDoc = snapshot[snapshotKey]!
            else { return ContentTypes.VerifyResponse(result: false, description: DocComparison.FailDescriptions.case5(docID: change.documentID, qualifiedCollection: change.collection)) }
            
            let mutableSnapshotDoc = snapshotDoc.toMutable()
            
            try DocumentUpdater.update(doc: mutableSnapshotDoc, updatedProperties: change.updatedProperties, removedProperties: change.removedProperties, updatedBlobs: change.updatedBlobs)
            
            let compareResult = try DocComparison.isEqual(mutableSnapshotDoc, existingDoc, docID: change.documentID, qualifiedCollection: change.collection)
            if(!compareResult.result) {
                return compareResult
            }
        }
        
        return ContentTypes.VerifyResponse(result: true, description: "Successfully verified changes.")
    }
}
