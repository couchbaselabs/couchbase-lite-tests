//
//  StartReplicatorRequest.swift
//  CBL-Tests-iOS
//
//  Created by Jim Borden on 3/6/2025
//

import Vapor

extension ContentTypes {
    struct StartListenerRequest : Content {
        let database: String
        let collections: [String]
        let port: UInt16?
        
        public var description: String {
            var result: String = "Endpoint Listener Configuration:\n"
            result += "\tdatabase: \(database)\n"
            result += "\tcollection: \(collections.joined(separator: ", "))\n"
            result += "\tport: \(port ?? 0)\n"
            return result
        }
    }
}
