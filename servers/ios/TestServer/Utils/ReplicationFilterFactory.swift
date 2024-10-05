//
//  ReplicationFilterFactory.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Foundation
import CouchbaseLiteSwift

struct ReplicationFilterFactory {
    static func documentIDs(params: Dictionary<String, AnyCodable>?) throws -> ReplicationFilter {
        guard let docIDsWrapped = params?["documentIDs"]
        else { throw TestServerError.badRequest("Could not find key 'documentIDs' in params.") }
        
        // docIDs should be a dictionary of collection name to array of docID
        guard let validDocIDs = docIDsWrapped.value as? [String : [String]]
        else { throw TestServerError.badRequest("documentIDs should be a Dict<String, Arr<String>>.") }
        
        return { document, _ in
            return validDocIDs.contains(where: { (_, docIDs) in docIDs.contains(document.id) })
        }
    }
    
    static func deletedDocumentsOnly() throws -> ReplicationFilter {
        return { _, docFlags in
            return docFlags == .deleted
        }
    }
    
    private enum availableFilters : String {
        case documentIDs = "documentIDs"
        case deletedDocumentsOnly = "deletedDocumentsOnly"
    }
    
    static func getFilter(withName name: String, params: Dictionary<String, AnyCodable>? = nil) throws -> ReplicationFilter {
        guard let filter = availableFilters(rawValue: name)
        else { throw TestServerError.badRequest("Could not find filter with name '\(name)'") }
        
        switch filter {
        case .documentIDs:
            return try documentIDs(params: params)
        case .deletedDocumentsOnly:
            return try deletedDocumentsOnly()
        }
    }
}
