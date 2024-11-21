//
//  VerifyDocuments.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import Vapor

extension Handlers {
    static let verifyDocuments : EndpointHandler<ContentTypes.VerifyResponse> = { req throws in
        guard let verifyRequest = try? req.content.decode(ContentTypes.VerifyRequest.self) else {
            throw TestServerError.badRequest("Request body is not a valid Verify Request.")
        }
        
        let dbManager = req.application.databaseManager
        return try Snapshot.verifyChanges(dbManager: dbManager,
                                          dbName: verifyRequest.database,
                                          snapshotID: verifyRequest.snapshot,
                                          changes: verifyRequest.changes)
    }
}
