//
//  StopReplicator.swift
//  TestServer
//
//  Created by Jim Borden on 3/6/2025.
//


import Vapor

extension Handlers {
    static let stopListener: EndpointHandlerEmptyResponse = { req throws in
        guard let requestedEndpointListener = try? req.content.decode(ContentTypes.Listener.self) else {
            throw TestServerError.badRequest("Request body does not match the 'Listener' schema.")
        }
        
        let dbManager = req.databaseManager
        try dbManager.stopListener(forID: requestedEndpointListener.id)
        
        return Response(status: .ok)
    }
}
