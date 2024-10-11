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
        guard let updateRequest = try? req.content.decode(ContentTypes.UpdateRequest.self)
        else {
            TestServer.logger.log(level: .error, "Request body is not a valid /updateDatabase request.")
            throw TestServerError.badRequest("Request body is not a valid Update request.")
        }

        let dbManager = try req.databaseManager()
        
        for update in updateRequest.updates {
            switch(update.type) {
            case .UPDATE:
                try DocumentUpdater.processUpdate(dbManager:dbManager, item: update, inDB: updateRequest.database)
            case .DELETE:
                guard let collection = try dbManager.collection(update.collection, inDB: updateRequest.database) else {
                    TestServer.logger.log(level: .error, "Failed to perform delete, collection '\(update.collection)' not found in database '\(updateRequest.database)'")
                    throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Collection '\(update.collection)' not found in database '\(updateRequest.database)'")
                }
                
                guard let doc = try? collection.document(id: update.documentID) else {
                    TestServer.logger.log(level: .error, "Failed to perform delete, document '\(update.documentID)' not found")
                    throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Document '\(update.documentID)' not found")
                }
                
                do {
                    try collection.delete(document: doc)
                } catch(let error as NSError) {
                    TestServer.logger.log(level: .error, "Failed to perform delete, CBL error: \(error)")
                    throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
                }
                
            case .PURGE:
                guard let collection = try dbManager.collection(update.collection, inDB: updateRequest.database) else {
                    TestServer.logger.log(level: .error, "Failed to perform purge, collection '\(update.collection)' not found in database '\(updateRequest.database)'")
                    throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Collection '\(update.collection)' not found in database '\(updateRequest.database)'")
                }
                
                guard let doc = try? collection.document(id: update.documentID) else {
                    TestServer.logger.log(level: .error, "Failed to perform purge, document '\(update.documentID)' not found")
                    throw TestServerError(domain: .CBL, code: CBLError.notFound, message: "Document '\(update.documentID)' not found")
                }
                
                do {
                    try collection.purge(document: doc)
                } catch(let error as NSError) {
                    TestServer.logger.log(level: .error, "Failed to perform purge, CBL error: \(error)")
                    throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
                }
            }
        }
        
        return Response(status: .ok)
    }
}

