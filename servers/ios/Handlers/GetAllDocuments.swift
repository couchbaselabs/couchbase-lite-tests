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
        guard let collections = try? req.content.decode(ContentTypes.Collections.self)
        else {
            throw TestServerError.badRequest
        }
        return try getCollectionsDocuments(collections: collections.collections)
    }
}

fileprivate func getCollectionsDocuments(collections: [String]) throws -> ContentTypes.CollectionDocuments {
    var result = ContentTypes.CollectionDocuments()
    guard let dbManager = DatabaseManager.shared
    else { throw TestServerError.cblDBNotOpen }
    for collectionName in collections {
        guard let query = dbManager.createQuery(queryString: "SELECT meta().id, meta().revisionID FROM \(collectionName)")
        else { throw TestServerError(domain: .CBL, code: CBLError.invalidQuery, message: "Failed to create docs query.") }
        guard let collectionDocs = try? query.execute().map({ result in ContentTypes.CollectionDoc(id: result.string(at: 0)!, rev: result.string(at: 1)!) })
        else { throw TestServerError(domain: .CBL, code: CBLError.invalidQuery, message: "Failed to execute docs query.") }
        result[collectionName] = collectionDocs
    }
    return result
}
