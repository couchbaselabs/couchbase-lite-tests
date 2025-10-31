//
//  GetDocument.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/3/24.
//

import Vapor
import CouchbaseLiteSwift

extension Handlers {
    static let getDocument: EndpointHandlerEmptyResponse = { req throws in
        guard let getDoc = try? req.content.decode(ContentTypes.GetDocumentRequest.self) else {
            throw TestServerError.badRequest("Request body does not match the 'GetDocument' scheme.")
        }
        
        let dbManager = req.databaseManager
        let json = try document(dbManager: dbManager,
                                id: getDoc.document.id,
                                collection: getDoc.document.collection,
                                database: getDoc.database)
        
        let response = Response(status: .ok)
        response.body = .init(data: try JSONEncoder().encode(json))
        response.headers.contentType = .json
        return response
    }
}

fileprivate func document(dbManager: DatabaseManager, id: String, collection: String, database: String) throws -> Dictionary<String, AnyCodable> {
    guard let doc = try dbManager.getDocument(id, fromCollection: collection, inDB: database) else {
        throw TestServerError.docNotFoundErr
    }
    
    var dict = doc.toDictionary()
    dict["_id"] = doc.id
    dict["_revs"] = doc._getRevisionHistory()
    
    let result = try dict.mapValues { try AnyCodable($0) }
    return result
}

