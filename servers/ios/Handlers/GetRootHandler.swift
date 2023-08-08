//
//  GetRootHandler.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

extension Handlers {
    static let getRoot : EndpointHandler<String> = { req throws in
        return "It works!"
    }
}
