//
//  LogHandler.swift
//  TestServer
//

import Vapor

extension ContentTypes {
    struct LogRequest : Content {
        let message: String
    }
}

extension Handlers {
    static let log: EndpointHandlerEmptyResponse = { req throws in
        guard let logRequest = try? req.content.decode(ContentTypes.LogRequest.self) else {
            throw TestServerError.badRequest("Request body does not match the 'LogRequest' schema.")
        }

        Log.log(level: .info, message: logRequest.message)
        return Response(status: .ok)
    }
}
