//
//  ResetHandler.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

extension Handlers {
    static let resetHandler: EndpointHandlerEmptyResponse = { req throws in
        let dbManager = req.databaseManager
        try dbManager.reset()
        
        if let config = try? req.content.decode(ContentTypes.ResetConfiguration.self), let databases = config.databases {
            for (dbName, spec) in databases {
                if spec["dataset"] != nil && spec["collections"] != nil {
                    throw TestServerError.badRequest("Invalid Reset Spec, dataset and collection cannot both be specified.")
                }
                
                if let dataset = spec["dataset"]?.value as? String {
                    try dbManager.createDatabase(dbName: dbName, dataset: dataset)
                } else if let collections = spec["collections"]?.value as? [String] {
                    try dbManager.createDatabase(dbName: dbName, collections: collections)
                } else {
                    try dbManager.createDatabase(dbName: dbName)
                }
            }
        }
        
        return Response(status: .ok)
    }
}
