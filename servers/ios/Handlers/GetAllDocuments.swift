//
//  GetAllDocuments.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import Vapor
import CouchbaseLiteSwift

extension Handlers {
    static let getAllDocuments: EndpointHandler<ContentTypes.CollectionDocuments> = { req throws in
        guard let collections = try? req.query.decode(ContentTypes.Collections.self)
        else {
            throw TestServerError.badRequest
        }
        guard let collectionDocs = ContentTypes.CollectionDocuments(collectionNames: collections.collections),
              collectionDocs.count > 0
        else {
            throw TestServerError(domain: .TESTSERVER, code: 500, message: "Internal server error.")
        }
        return collectionDocs
    }
}
