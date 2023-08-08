//
//  ResetHandler.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

extension Handlers {
    static let resetHandler: EndpointHandlerEmptyResponse = { req throws in
        if let databaseManager = DatabaseManager.shared {
            do {
                try databaseManager.reset()
                return Response(status: .ok)
            } catch let error as TestServerError {
                throw error
            }
        }
        else {
            throw TestServerError.cblDBNotOpen
        }
    }
}
