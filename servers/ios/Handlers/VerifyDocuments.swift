//
//  VerifyDocuments.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import Vapor

extension Handlers {
    static let verifyDocuments : EndpointHandler<ContentTypes.VerifyResponse> = { req throws in
        guard let verifyRequest = try? req.content.decode(ContentTypes.VerifyRequest.self)
        else { throw TestServerError.badRequest("Request body is not a valid Verify Request.") }
        
        let result = try Snapshot.verifyChanges(dbName: verifyRequest.database, snapshotID: verifyRequest.snapshot, changes: verifyRequest.changes)
        print(result)
        return result
    }
}
