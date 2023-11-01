//
//  SnapshotRequest.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import Vapor

extension ContentTypes {
    struct SnapshotRequest : Content {
        let database: String
        let documents: Array<DocumentID>
    }
}
