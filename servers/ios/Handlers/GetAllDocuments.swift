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
        return try getCollectionsDocuments(database: collections.database, collections: collections.collections)
    }
}

fileprivate func getCollectionsDocuments(database: String, collections: [String]) throws -> ContentTypes.CollectionDocuments {
    var result = ContentTypes.CollectionDocuments()
    guard let dbManager = DatabaseManager.shared
    else { throw TestServerError.cblDBNotOpen }
    for collectionName in collections {
        let queryResult = try dbManager.runQuery(dbName: database, queryString: "SELECT meta().id, meta().revisionID FROM \(collectionName)")
        let collectionDocs = queryResult.map({ result in ContentTypes.CollectionDoc(id: result.string(at: 0)!, rev: result.string(at: 1)!) })
        result[collectionName] = collectionDocs
    }
    return result
}
