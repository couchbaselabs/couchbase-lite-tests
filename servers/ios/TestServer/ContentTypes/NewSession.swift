//
//  NewSession.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/11/24.
//

import Vapor

extension ContentTypes {
    struct Logging : Content {
        let url: String
        let tag: String
    }
    
    struct NewSession : Content {
        let id: String
        let dataset_version: String
        let logging: Logging?
    }
}
