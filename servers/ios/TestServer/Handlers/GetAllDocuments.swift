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
        guard let collections = try? req.content.decode(ContentTypes.Collections.self) else {
            throw TestServerError.badRequest("Request body does not match the 'Collections' scheme.")
        }
        
        let dbManager = req.application.databaseManager
        return try getCollectionsDocuments(dbManager: dbManager,
                                           database: collections.database,
                                           collections: collections.collections)
    }
}

fileprivate func getCollectionsDocuments(dbManager: DatabaseManager, database: String, collections: [String]) throws -> ContentTypes.CollectionDocuments {
    var result = ContentTypes.CollectionDocuments()
    for collectionName in collections {
        let queryResult = try dbManager.runQuery(dbName: database, queryString: "SELECT meta().id, meta().revisionID FROM \(collectionName)")
        let collectionDocs = queryResult.map({ result in ContentTypes.CollectionDoc(id: result.string(at: 0)!, rev: result.string(at: 1)!) })
        result[collectionName] = collectionDocs
    }
    return result
}
