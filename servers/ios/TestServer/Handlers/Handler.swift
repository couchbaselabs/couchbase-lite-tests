//
//  Handler.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

typealias EndpointHandler<T: Content> = (Request) throws -> T
typealias EndpointHandlerEmptyResponse = (Request) throws -> Response

struct Handlers { }

extension Request {
    func databaseManager() throws -> DatabaseManager {
        guard let session = self.storage.get(SessionKey.self) else {
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "Session Not Found")
        }
        return session.databaseManager
    }
}
