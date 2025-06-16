//
//  GetMultipeerReplicatorStatus.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 6/2/25.
//

import Foundation

extension Handlers {
    static let getMultipperReplicatorStatus : EndpointHandler<ContentTypes.MultipeerReplicatorStatus> = { req throws in
        guard let repl = try? req.content.decode(ContentTypes.Replicator.self) else {
            throw TestServerError.badRequest("Request body does not match the 'Replicator' schema.") }
        
        let dbManager = req.application.databaseManager
        guard let status = dbManager.multipeerReplicatorStatus(forID: repl.id) else {
            throw TestServerError.badRequest("MultipeerReplicator with ID '\(repl.id)' does not exist.")
        }
        return status
    }
}
