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
    
    static func saveSnapshot(dbManager: DatabaseManager, dbName: String, docIDs: [ContentTypes.DocumentID]) throws -> UUID {
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
    
    static func verifyChanges(dbManager: DatabaseManager, dbName: String, snapshotID: String,
                              changes: [ContentTypes.DatabaseUpdateItem]) throws -> ContentTypes.VerifyResponse {
        guard let uuid = UUID(uuidString: snapshotID), let snapshot = currentSnapshots[uuid] else {
            throw TestServerError.badRequest("Snapshot with ID '\(snapshotID)' does not exist.")
        }
        
        var verifiedSnapshotDocs: Set<String> = []
        
        // Verify changes:
        for change in changes {
            let snapshotKey = "\(change.collection).\(change.documentID)"
            
            verifiedSnapshotDocs.insert(snapshotKey)
            
            guard snapshot.keys.contains(snapshotKey) else {
                throw TestServerError.badRequest("Snapshot '\(snapshotID)' does not contain key '\(change.collection).\(change.documentID)'")
            }
            
            guard let collection = try dbManager.collection(change.collection, inDB: dbName) else {
                throw TestServerError.badRequest("Cannot find collection '\(change.collection)' in db '\(dbName)'")
            }
            
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
            
            guard let existingDoc = existingDoc else {
                return ContentTypes.VerifyResponse(result: false, description: DocComparison.FailDescriptions.case1(docID: change.documentID, qualifiedCollection: change.collection))
            }
            
            let snapshotDoc = snapshot[snapshotKey]!
            let mutableSnapshotDoc = snapshotDoc != nil ? snapshotDoc!.toMutable() : MutableDocument(id: change.documentID)
            try DocumentUpdater.update(
                dbManager: dbManager,
                doc: mutableSnapshotDoc,
                updatedProperties: change.updatedProperties,
                removedProperties: change.removedProperties,
                updatedBlobs: change.updatedBlobs)
            
            let compareResult = try DocComparison.isEqual(mutableSnapshotDoc, existingDoc, docID: change.documentID,
                                                          qualifiedCollection: change.collection)
            if(!compareResult.result) {
                return compareResult
            }
        }
        
        // Verify unchanged docs:
        for (key, doc) in snapshot {
            // Check if already verified:
            if verifiedSnapshotDocs.contains(key) {
                continue;
            }
            
            let comps = key.components(separatedBy: ".")
            if comps.count != 3 {
                throw TestServerError.badRequest("Invalid snapshot key: \(key)")
            }
            
            let collName = "\(comps[0]).\(comps[1])"
            let docID = comps[2]
            
            let existingDoc = try dbManager.getDocument(docID, fromCollection: collName, inDB: dbName)
            if let snapdoc = doc {
                guard let existingDoc = existingDoc else {
                    let desc = DocComparison.FailDescriptions.case1(docID: docID, qualifiedCollection: collName)
                    return ContentTypes.VerifyResponse(result: false, description: desc)
                }
                let compareResult = try DocComparison.isEqual(snapdoc, existingDoc, docID: docID,
                                                              qualifiedCollection: collName)
                if(!compareResult.result) {
                    return compareResult
                }
            } else {
                if existingDoc != nil {
                    let desc = DocComparison.FailDescriptions.case5(docID: docID, qualifiedCollection: collName)
                    return ContentTypes.VerifyResponse(result: false, description: desc)
                }
            }
        }
        
        return ContentTypes.VerifyResponse(result: true, description: "Successfully verified changes.")
    }
}
