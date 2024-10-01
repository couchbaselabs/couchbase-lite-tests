//
//  RunQueryConfiguration.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 9/25/24.
//

import Vapor

extension ContentTypes {
    struct RunQueryConfiguration : Content {
        let database: String
        let query: String
    }
}
