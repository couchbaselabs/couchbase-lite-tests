//
//  PerformMaintenanceConfiguration.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 19/09/2023.
//

import Vapor

extension ContentTypes {
    struct PerformMaintenanceConfiguration : Content {
        enum MaintenanceType : String, Codable {
            case compact = "compact"
            case integrityCheck = "integrityCheck"
            case optimize = "optimize"
            case fullOptimize = "fullOptimize"
        }
        
        let database: String
        let maintenanceType: MaintenanceType
    }
}
