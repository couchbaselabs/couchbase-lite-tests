//
//  StopMultipeerReplicator.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 5/30/25.
//

import Vapor

extension Handlers {
    static let stopMultipeerReplicator: EndpointHandlerEmptyResponse = { req throws in
        guard let requestedReplicator = try? req.content.decode(ContentTypes.Replicator.self) else {
            throw TestServerError.badRequest("Request body does not match the 'Replicator' schema.")
        }
        
        let dbManager = req.application.databaseManager
        try dbManager.stopMultipeerReplicator(forID: requestedReplicator.id)
        return Response(status: .ok)
    }
}
