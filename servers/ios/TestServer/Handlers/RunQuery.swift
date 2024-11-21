//
//  RunQuery.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 9/25/24.
//

import Vapor
import CouchbaseLiteSwift

extension Handlers {
    static let runQuery: EndpointHandler<ContentTypes.QueryResults> = { req throws in
        guard let config = try? req.content.decode(ContentTypes.RunQueryConfiguration.self) else {
            throw TestServerError.badRequest("Request body does not match the 'RunQueryConfiguration' scheme.")
        }
        
        let dbManager = req.application.databaseManager
        return try _runQuery(dbManager: dbManager, database: config.database, query: config.query)
    }
}

fileprivate func _runQuery(dbManager: DatabaseManager, database: String, query: String) throws -> ContentTypes.QueryResults {
    var results: Array<Dictionary<String, AnyCodable>> = []
    let queryResult = try dbManager.runQuery(dbName: database, queryString: query)
    for row in queryResult {
        let result: [String: AnyCodable] = try row.toDictionary().mapValues { try AnyCodable($0) }
        results.append(result)
    }
    return ContentTypes.QueryResults(results: results)
}
