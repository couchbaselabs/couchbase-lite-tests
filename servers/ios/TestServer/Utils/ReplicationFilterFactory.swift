//
//  ReplicationFilterFactory.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Foundation
import CouchbaseLiteSwift

struct AnyReplicationFilter {
    private let block: (PeerID?, Document, DocumentFlags) -> Bool

    init(_ block: @escaping (PeerID?, Document, DocumentFlags) -> Bool) {
        self.block = block
    }

    func toReplicationFilter() -> ReplicationFilter {
        return { doc, flags in self.block(nil, doc, flags) }
    }

    func toMultipeerReplicationFilter() -> MultipeerReplicationFilter {
        return { peerID, doc, flags in self.block(peerID, doc, flags) }
    }
}

struct ReplicationFilterFactory {
    static func documentIDs(params: Dictionary<String, AnyCodable>?) throws -> AnyReplicationFilter {
        guard let docIDsWrapped = params?["documentIDs"] else {
            throw TestServerError.badRequest("Could not find key 'documentIDs' in params.")
        }
        
        // docIDs should be a dictionary of collection name to array of docID
        guard let validDocIDs = docIDsWrapped.value as? [String : [String]] else {
            throw TestServerError.badRequest("documentIDs should be a Dict<String, Arr<String>>.")
        }
        
        return AnyReplicationFilter({ _, document, _ in
            return validDocIDs.contains(where: { (_, docIDs) in docIDs.contains(document.id) })
        })
    }
    
    static func deletedDocumentsOnly() throws -> AnyReplicationFilter {
        return AnyReplicationFilter({ _, _, docFlags in
            return docFlags == .deleted
        })
    }
    
    private enum availableFilters : String {
        case documentIDs = "documentIDs"
        case deletedDocumentsOnly = "deletedDocumentsOnly"
    }
    
    static func getFilter(withName name: String, params: Dictionary<String, AnyCodable>? = nil) throws -> AnyReplicationFilter {
        guard let filter = availableFilters(rawValue: name) else {
            throw TestServerError.badRequest("Could not find filter with name '\(name)'")
        }
        
        switch filter {
        case .documentIDs:
            return try documentIDs(params: params)
        case .deletedDocumentsOnly:
            return try deletedDocumentsOnly()
        }
    }
}
