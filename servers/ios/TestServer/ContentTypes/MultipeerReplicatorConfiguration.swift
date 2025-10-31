//
//  MultipeerReplicatorConfiguration.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 5/30/25.
//

import Vapor

extension ContentTypes {
    struct MultipeerReplicatorConfiguration : Content {
        let peerGroupID: String
        let database: String
        let collections: [ReplicationCollection]
        let identity: MultipeerReplicatorIdentity
        let authenticator: MultipeerReplicatorCAAuthenticator?
    }
}
