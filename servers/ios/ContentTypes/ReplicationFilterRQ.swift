//
//  ReplicationFilter.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor

extension ContentTypes {
    struct ReplicationFilter : Content {
        let name: String
        let params: Dictionary<String, AnyCodable>?
    }
}
