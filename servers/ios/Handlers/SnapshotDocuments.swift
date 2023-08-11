//
//  SnapshotDocuments.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import Vapor

extension Handlers {
    static let snapshotDocuments: EndpointHandler<ContentTypes.SnapshotID> = { req throws in
        guard let snapshotRequest = try? req.content.decode(ContentTypes.SnapshotRequest.self)
        else { throw TestServerError.badRequest }
        
        let snapshotID = try Snapshot.saveSnapshot(dbName: snapshotRequest.database, docIDs: snapshotRequest.documents)
        
        return ContentTypes.SnapshotID(id: snapshotID)
    }
}
