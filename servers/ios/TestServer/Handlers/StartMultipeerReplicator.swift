//
//  StartMultipeerReplicator.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 5/30/25.
//

import Foundation

extension Handlers {
    static let startMultipeerReplicator: EndpointHandler<ContentTypes.Replicator> = { req throws in
        guard let request = try? req.content.decode(ContentTypes.StartMultipeerReplicatorRequest.self) else {
            throw TestServerError.badRequest("Request body is not a valid startMultipeerReplicator Request.")
        }
        
        let dbManager = req.application.databaseManager
        
        var config = ContentTypes.MultipeerReplicatorConfiguration(
            peerGroupID: request.peerGroupID,
            database: request.database,
            collections: request.collections)
        
        let id = try dbManager.startMultipeerReplicator(config: config)
        
        return ContentTypes.Replicator(id: id)
    }
}
