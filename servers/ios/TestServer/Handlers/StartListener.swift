//
//  StartReplicator.swift
//  CBL-Tests-iOS
//
//  Created by Jim Borden on 03/06/2025.
//

import Foundation

extension Handlers {
    static let startListener: EndpointHandler<ContentTypes.Listener> = { req throws in
        // TODO: Implement this
        
        return ContentTypes.Listener(id: 'invalid', port: 0)
    }
}
