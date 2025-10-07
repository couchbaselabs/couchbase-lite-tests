//
//  ReplicatorStatus.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor
import CouchbaseLiteSwift

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

extension ContentTypes.ReplicatorActivity {
    init(activityLevel: Replicator.ActivityLevel) {
        switch activityLevel {
        case .busy:
            self = .BUSY
        case .connecting:
            self = .CONNECTING
        case .idle:
            self = .IDLE
        case .offline:
            self = .OFFLINE
        case .stopped:
            self = .STOPPED
        @unknown default:
            fatalError("Encountered unknown enum value from Replicator.status.activity")
        }
    }
}

extension ContentTypes.ReplicatorStatus {
    init(status: Replicator.Status, docs: [ContentTypes.DocumentReplication]) {
        self.activity = ContentTypes.ReplicatorActivity(activityLevel: status.activity)
        self.progress = ContentTypes.ReplicatorStatus.Progress(
            completed: status.progress.completed == status.progress.total)
        self.documents = docs
        self.error = status.error.map(TestServerError.cblError)
    }
}
