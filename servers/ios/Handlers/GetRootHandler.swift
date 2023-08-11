//
//  GetRootHandler.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

extension Handlers {
    static let getRoot : EndpointHandler<ContentTypes.ServerInfo> = { req throws in
        return ContentTypes.ServerInfo()
    }
}
