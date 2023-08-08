//
//  ErrorMiddleware.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor
import CouchbaseLiteSwift

class TestServerErrorMiddleware : Middleware {
    private func EncodeErrorResponse(request: Request, status: HTTPStatus, headers: HTTPHeaders, error: TestServerError) -> Response {
        let response = Response(status: status, headers: headers)
        do {
            response.body = try .init(data: JSONEncoder().encode(error), byteBufferAllocator: request.byteBufferAllocator)
            response.headers.replaceOrAdd(name: .contentType, value: "application/json; charset=utf-8")
        } catch {
            response.body = .init(string: "Oops: \(error)", byteBufferAllocator: request.byteBufferAllocator)
            response.headers.replaceOrAdd(name: .contentType, value: "text/plain; charset=utf-8")
        }
        return response
    }
    
    private func CreateErrorResponse(_ request: Request, _ error: TestServerError) -> Response {
        // Test server errors are 500 Internal, other errors are 400 Bad Request
        let status: HTTPStatus = error.domain == .TESTSERVER ? .internalServerError : .badRequest
        let headers: HTTPHeaders = [:]
        
        return EncodeErrorResponse(request: request, status: status, headers: headers, error: error)
    }
    
    private func DefaultErrorResponse(_ request: Request) -> Response {
        let error = TestServerError(domain: .TESTSERVER,
                                    code: 500,
                                    message: "Failed to handle internal error.")
        
        let status: HTTPStatus = .internalServerError
        let headers: HTTPHeaders = [:]
        
        request.logger.error(Logger.Message(stringLiteral: error.message))
        
        return EncodeErrorResponse(request: request, status: status, headers: headers, error: error)
    }
    
    public func respond(to request: Vapor.Request, chainingTo next: Vapor.Responder) -> NIOCore.EventLoopFuture<Vapor.Response> {
        next.respond(to: request).flatMapErrorThrowing { error in
            if let error = error as? TestServerError {
                return self.CreateErrorResponse(request, error)
            } else {
                return self.DefaultErrorResponse(request)
            }
            
        }
    }
}
