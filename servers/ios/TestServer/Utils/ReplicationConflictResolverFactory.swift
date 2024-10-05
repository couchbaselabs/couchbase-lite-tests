//
//  ReplicationConflictResolverFactory.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/3/24.
//

import Foundation
import CouchbaseLiteSwift

struct ReplicationConflictResolverFactory {
    struct LocalWinsResolver : ConflictResolverProtocol {
        func resolve(conflict: Conflict) -> Document? {
            return conflict.localDocument
        }
    }
    
    struct RemoteWinsResolver : ConflictResolverProtocol {
        func resolve(conflict: Conflict) -> Document? {
            return conflict.remoteDocument
        }
    }
    
    struct DeleteResolver : ConflictResolverProtocol {
        func resolve(conflict: Conflict) -> Document? {
            return nil
        }
    }
    
    struct MergeResolver : ConflictResolverProtocol {
        let property: String
        
        func resolve(conflict: Conflict) -> Document? {
            let mergedValues = MutableArrayObject()
            
            if let doc = conflict.localDocument, let value = doc.value(forKey: property) {
                mergedValues.addValue(value)
            }
            
            if let doc = conflict.remoteDocument, let value = doc.value(forKey: property) {
                mergedValues.addValue(value)
            }
            
            let doc = conflict.remoteDocument != nil ?
                conflict.remoteDocument!.toMutable() :
                conflict.localDocument!.toMutable()
            
            return doc.setValue(mergedValues, forKey: property)
        }
    }
    
    private enum ConflictResolverType : String {
        case localWins = "local-wins"
        case removeWins = "remote-wins"
        case delete = "delete"
        case merge = "merge"
    }
    
    static func getResolver(withName name: String, params: Dictionary<String, AnyCodable>? = nil)
    throws -> ConflictResolverProtocol {
        guard let type = ConflictResolverType(rawValue: name) else {
            throw TestServerError.badRequest("Could not find conflict resolver with name '\(name)'")
        }
        
        switch type {
        case .localWins:
            return LocalWinsResolver()
        case .removeWins:
            return RemoteWinsResolver()
        case .delete:
            return DeleteResolver()
        case .merge:
            guard let property = params?["property"]?.value as? String else {
                throw TestServerError.badRequest("The property parameter is missing for the merge conflict resolver")
            }
            return MergeResolver(property: property)
        }
    }
}

