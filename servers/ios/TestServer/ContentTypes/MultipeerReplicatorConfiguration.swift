//
//  MultipeerReplicatorConfiguration.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 5/30/25.
//

import Foundation

import Vapor

extension ContentTypes {
    struct MultipeerReplicatorConfiguration : Content {
        let peerGroupID: String
        let database: String
        let collections: [ReplicationCollection]
    }
}
