//
//  ResetHandler.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

extension Handlers {
    static let resetHandler: EndpointHandlerEmptyResponse = { req throws in
        guard let databaseManager = DatabaseManager.shared
        else {
            throw TestServerError.cblDBNotOpen
        }
        
        if let resetConfig = try? req.content.decode(ContentTypes.ResetConfiguration.self),
           !resetConfig.datasets.isEmpty {
            let datasetName = resetConfig.datasets.keys.first!
            try databaseManager.reset(dataset: datasetName)
        } else {
            try databaseManager.reset()
        }
        
        return Response(status: .ok)
    }
}
