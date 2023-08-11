//
//  HeadersMiddleware.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 09/08/2023.
//

import Foundation
import Vapor

class HeadersMiddleware : AsyncMiddleware {
    func respond(to request: Vapor.Request, chainingTo next: Vapor.AsyncResponder) async throws -> Vapor.Response {
        
        print(request)
        
        let isGetRoot = request.route?.description == "GET /"
        
        var version = 0
        
        do {
            // Request headers aren't required for `GET /`
            version = isGetRoot ? 0 : try verifyHeaders(request.headers)
        } catch(let error as TestServerError) {
            // This middleware sits before the error middleware, so we have to create this
            // error ourselves
            let response = ErrorResponseFactory.CreateErrorResponse(request, error)
            return withResponseHeaders(response, version: version)
        }
        
        request.headers.contentType = .json
        
        let response = try await next.respond(to: request)
        
        print(response)
        
        return withResponseHeaders(response, version: version)
    }
    
    func withResponseHeaders(_ response: Response, version: Int) -> Response {
        let resolvedVersion = version != 0 ? version : TestServer.maxAPIVersion
        response.headers.add(name: "CBLTest-Server-ID", value: TestServer.serverID.uuidString)
        response.headers.add(name: "CBLTest-API-Version", value: "\(resolvedVersion)")
        return response
    }
    
    private func verifyHeaders(_ headers: HTTPHeaders) throws -> Int {
        guard headers.contains(name: "CBLTest-Client-ID"),
              let versionStr = headers.first(name: "CBLTest-API-Version"),
              let version = Int(versionStr)
        else {
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "Missing headers.")
        }
        
        if(version > TestServer.maxAPIVersion) {
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "The API version specified is not supported.")
        }
        
        return version
    }
}
