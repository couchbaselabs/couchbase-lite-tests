//
//  StartReplicator.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Foundation

extension Handlers {
    static let startReplicator: EndpointHandler<ContentTypes.Replicator> = { req throws in
        guard let replStartRq = try? req.content.decode(ContentTypes.StartReplicatorRequest.self)
        else { throw TestServerError.badRequest }
        
        guard let dbManager = DatabaseManager.shared
        else { throw TestServerError.cblDBNotOpen }
        
        return ContentTypes.Replicator(id: try dbManager.startReplicator(config: replStartRq.config, reset: replStartRq.reset ?? false))
    }
}
