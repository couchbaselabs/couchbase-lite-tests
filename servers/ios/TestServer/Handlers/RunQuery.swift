//
//  RunQuery.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 9/25/24.
//

import Vapor
import CouchbaseLiteSwift

extension Handlers {
    static let runQuery: EndpointHandler<ContentTypes.RunQueryConfiguration> = { req throws in
        guard let config = try? req.content.decode(ContentTypes.RunQueryConfiguration.self)
        else {
            throw TestServerError.badRequest("Request body does not match the 'RunQueryConfiguration' scheme.")
        }
        return try runQuery(database: config.database, query: config.query)
    }
}

fileprivate func runQuery(database: String, query: String) throws -> ContentTypes.CollectionDocuments {
    var result = ContentTypes.CollectionDocuments()
    guard let dbManager = DatabaseManager.shared
    else { throw TestServerError.cblDBNotOpen }
    
    let queryResult = try dbManager.runQuery(dbName: database, queryString: query)
    
    
                                             
    
    for collectionName in collections {
        let queryResult = try dbManager.runQuery(dbName: database, queryString: "SELECT meta().id, meta().revisionID FROM \(collectionName)")
        let collectionDocs = queryResult.map({ result in ContentTypes.CollectionDoc(id: result.string(at: 0)!, rev: result.string(at: 1)!) })
        result[collectionName] = collectionDocs
    }
    return result
}
