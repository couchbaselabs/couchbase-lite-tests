//
//  ReplicatorStatus.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor

extension ContentTypes {
    enum ReplicatorActivity : String, Codable {
        case STOPPED = "STOPPED"
        case OFFLINE = "OFFLINE"
        case CONNECTING = "CONNECTING"
        case IDLE = "IDLE"
        case BUSY = "BUSY"
    }
    struct ReplicatorStatus : Content {
        struct Progress : Codable {
            let completed: Bool
        }
        let activity: ReplicatorActivity
        let progress: Progress
        let documents: [DocumentReplication]?
        let error: TestServerError?
    }
}
