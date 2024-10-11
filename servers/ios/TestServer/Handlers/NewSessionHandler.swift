//
//  NewSessionHandler.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/11/24.
//

import Vapor

extension Handlers {
    static let newSession: EndpointHandlerEmptyResponse = { req throws in
        // TODO: Implement stream logging
        return Response(status: .ok)
    }
}
