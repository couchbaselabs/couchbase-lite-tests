//
//  ReplicationConflictResolver.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/3/24.
//

import Vapor

extension ContentTypes {
    struct ReplicationConflictResolver : Content {
        let name: String
        let params: Dictionary<String, AnyCodable>?
    }
}
