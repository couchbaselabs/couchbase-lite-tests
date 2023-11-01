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
    struct ReplicatorStatus : Content, CustomStringConvertible {
        struct Progress : Codable {
            let completed: Bool
        }
        let activity: ReplicatorActivity
        let progress: Progress
        let documents: [DocumentReplication]?
        let error: TestServerError?
        
        var description: String {
            var result = ""
            
            result += "ReplicatorStatus: \n"
            result += "\tactivity: \(activity.rawValue)\n"
            result += "\tprogress: completed: \(progress.completed.description)\n"
            result += "\tdocuments: \(documents.debugDescription)\n"
            
            result += "\terror: \(error.debugDescription)"
            
            return result
        }
    }
}
