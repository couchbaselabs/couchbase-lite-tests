//
//  StartReplicator.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Foundation

extension Handlers {
    static let startReplicator: EndpointHandler<ContentTypes.Replicator> = { req throws in
        guard let replStartRq = try? req.content.decode(ContentTypes.StartReplicatorRequest.self) else {
            throw TestServerError.badRequest("Request body is not a valid startReplicator Request.")
        }
        
        let dbManager = req.databaseManager
        let reset = replStartRq.reset ?? false
        let id = try dbManager.startReplicator(config: replStartRq.config, reset: reset)
        return ContentTypes.Replicator(id: id)
    }
}
