//
//  StartReplicator.swift
//  CBL-Tests-iOS
//
//  Created by Jim Borden on 03/06/2025.
//

import Foundation

extension Handlers {
    static let startListener: EndpointHandler<ContentTypes.Listener> = { req throws in
        guard let listenerStartRq = try? req.content.decode(ContentTypes.StartListenerRequest.self) else {
            throw TestServerError.badRequest("Request body is not a valid startListener Request.")
        }
        
        Log.log(level: .debug, message: "Starting Listener with config: \(listenerStartRq.description)")
        
        let dbManager = req.databaseManager
        let disableTLS = listenerStartRq.disableTLS ?? false
        let id = try dbManager.startListener(dbName: listenerStartRq.database, collections: listenerStartRq.collections, port: listenerStartRq.port, disableTLS: disableTLS,identity: request.identity)
        
        return ContentTypes.Listener(id: id, port: listenerStartRq.port)
    }
}
