//
//  ReplicationConflictResolverFactory.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/3/24.
//

import Foundation
import CouchbaseLiteSwift

public protocol AnyConflictResolver {
    func resolve(peerID: PeerID?, conflict: Conflict) -> Document?
}

struct ConflictResolver: ConflictResolverProtocol, MultipeerConflictResolver {
    private let resolver: AnyConflictResolver
    
    init(_ resolver: AnyConflictResolver) {
        self.resolver = resolver
    }
    
    func resolve(conflict: Conflict) -> Document? {
        return resolver.resolve(peerID: nil, conflict: conflict)
    }
    
    func resolve(peerID: PeerID, conflict: Conflict) -> Document? {
        return resolver.resolve(peerID: peerID, conflict: conflict)
    }
}

struct ReplicationConflictResolverFactory {
    struct LocalWinsResolver : AnyConflictResolver {
        func resolve(peerID: PeerID?, conflict: Conflict) -> Document? {
            return conflict.localDocument
        }
    }
    
    struct RemoteWinsResolver : AnyConflictResolver {
        func resolve(peerID: PeerID?, conflict: Conflict) -> Document? {
            return conflict.remoteDocument
        }
    }
    
    struct DeleteResolver : AnyConflictResolver {
        func resolve(peerID: PeerID?, conflict: Conflict) -> Document? {
            return nil
        }
    }
    
    struct MergeResolver : AnyConflictResolver {
        let property: String
        
        func resolve(peerID: PeerID?, conflict: Conflict) -> Document? {
            if conflict.localDocument == nil || conflict.remoteDocument == nil {
                return nil
            }
            
            let mergedValues = MutableArrayObject()
            mergedValues.addValue(conflict.localDocument!.value(forKey: property))
            mergedValues.addValue(conflict.remoteDocument!.value(forKey: property))
            
            let doc = conflict.remoteDocument!.toMutable()
            return doc.setValue(mergedValues, forKey: property)
        }
    }
    
    private enum ConflictResolverType : String {
        case localWins = "local-wins"
        case removeWins = "remote-wins"
        case delete = "delete"
        case merge = "merge"
    }
    
    static func getResolver(
        withName name: String,
        params: Dictionary<String, AnyCodable>? = nil) throws -> ConflictResolver {
        guard let type = ConflictResolverType(rawValue: name) else {
            throw TestServerError.badRequest("Could not find conflict resolver with name '\(name)'")
        }
        
        switch type {
        case .localWins:
            return ConflictResolver(LocalWinsResolver())
        case .removeWins:
            return ConflictResolver(RemoteWinsResolver())
        case .delete:
            return ConflictResolver(DeleteResolver())
        case .merge:
            guard let property = params?["property"]?.value as? String else {
                throw TestServerError.badRequest("The property parameter is missing for the merge conflict resolver")
            }
            return ConflictResolver(MergeResolver(property: property))
        }
    }
}
