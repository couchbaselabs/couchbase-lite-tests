//
//  MultipeerReplicatorStatus.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 6/2/25.
//

import Vapor

extension ContentTypes {
    struct PeerReplicatorStatus : Content {
        let peerID: String
        let status: ReplicatorStatus
    }
    
    struct MultipeerReplicatorStatus : Content {
        let replicators: [PeerReplicatorStatus]
    }
}
