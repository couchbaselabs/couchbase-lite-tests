//
//  StopReplicator.swift
//  TestServer
//
//  Created by Jim Borden on 3/6/2025.
//


import Vapor

extension Handlers {
    static let stopReplicator: EndpointHandlerEmptyResponse = { req throws in
        // TODO: Implement this
        
        return Response(status: .ok)
    }
}
