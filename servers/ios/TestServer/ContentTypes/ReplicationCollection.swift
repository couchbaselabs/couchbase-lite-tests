//
//  ReplicationCollection.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor

extension ContentTypes {
    struct ReplicationCollection : Content {
        let names: [String]
        let channels: [String]?
        let documentIDs: [String]?
        let pushFilter: ReplicationFilter?
        let pullFilter: ReplicationFilter?
        let conflictResolver: ReplicationConflictResolver?
    }
}
