//
//  UpdateDatabase.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import Vapor
import CouchbaseLiteSwift

extension Handlers {
    static let updateDatabase : EndpointHandlerEmptyResponse = { req throws in
        guard let updateRequest = try? req.query.decode(ContentTypes.DatabaseUpdateItem.self)
        else {
            throw TestServerError.badRequest
        }
        
        switch(updateRequest.type) {
        case .UPDATE:
            DocumentUpdater.processUpdate(item: updateRequest)
        case .DELETE:
            guard let collection = DatabaseManager.shared?.collection(updateRequest.collection)
            else {
                throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Collection not found")
            }
            guard let doc = try? collection.document(id: updateRequest.documentID)
            else {
                throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Document not found")
            }
            try? collection.delete(document: doc)
        case .PURGE:
            guard let collection = DatabaseManager.shared?.collection(updateRequest.collection)
            else {
                throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Collection not found")
            }
            guard let doc = try? collection.document(id: updateRequest.documentID)
            else {
                throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Document not found")
            }
            try? collection.purge(document: doc)
        }
        return Response(status: .ok)
    }
}

