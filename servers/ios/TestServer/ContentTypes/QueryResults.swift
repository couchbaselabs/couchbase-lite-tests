//
//  QueryResults.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 9/25/24.
//

import Vapor

extension ContentTypes {
    struct QueryResults : Content {
        let results: Array<Dictionary<String, AnyCodable>>
    }
}
