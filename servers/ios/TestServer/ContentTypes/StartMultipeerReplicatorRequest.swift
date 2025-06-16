//
//  StartMultipeerReplicatorRequest.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 5/30/25.
//

import Vapor

extension ContentTypes {
    struct StartMultipeerReplicatorRequest : Content {
        let peerGroupID: String
        let database: String
        let collections: [ReplicationCollection]
    }
}
