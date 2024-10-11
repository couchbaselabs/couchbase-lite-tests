//
//  PerformMaintenance.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 19/09/2023.
//

import Vapor
import CouchbaseLiteSwift

extension Handlers {
    static let performMaintenance: EndpointHandlerEmptyResponse = { req throws in
        
        guard let maintenanceConfig = try? req.content.decode(ContentTypes.PerformMaintenanceConfiguration.self) else {
            throw TestServerError.badRequest("Invalid maintenance configuration.")
        }
        
        let dbManager = try req.databaseManager()
        let maintenaceType: CouchbaseLiteSwift.MaintenanceType = {
            switch maintenanceConfig.maintenanceType {
            case .compact: return .compact
            case .fullOptimize: return .fullOptimize
            case .integrityCheck: return .integrityCheck
            case .optimize: return .optimize
            }
        }()
        try dbManager.performMaintenance(type: maintenaceType, onDB: maintenanceConfig.database)
        
        return Response(status: .ok)
    }
}
