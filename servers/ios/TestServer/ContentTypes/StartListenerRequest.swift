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
        let port: Int?
    }
}
