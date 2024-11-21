//
//  Handler.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

typealias EndpointHandler<T: Content> = (Request) throws -> T
typealias EndpointHandlerEmptyResponse = (Request) throws -> Response

struct Handlers { }
