//
//  GetReplicatorStatus.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Foundation

extension Handlers {
    static let getReplicatorStatus : EndpointHandler<ContentTypes.ReplicatorStatus> = { req throws in
        guard let requestedReplicator = try? req.content.decode(ContentTypes.Replicator.self)
        else { throw TestServerError.badRequest }
        
        guard let dbManager = DatabaseManager.shared
        else { throw TestServerError.cblDBNotOpen }
        
        guard let replStatus = dbManager.replicatorStatus(forID: requestedReplicator.id)
        else { throw TestServerError.badRequest }
        
        return replStatus
    }
}
