//
//  StopReplicator.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 9/25/24.
//


import Vapor

extension Handlers {
    static let stopReplicator: EndpointHandlerEmptyResponse = { req throws in
        guard let requestedReplicator = try? req.content.decode(ContentTypes.Replicator.self) else {
            throw TestServerError.badRequest("Request body does not match the 'Replicator' schema.")
        }
        
        let dbManager = req.application.databaseManager
        try dbManager.stopReplicator(forID: requestedReplicator.id)
        return Response(status: .ok)
    }
}
