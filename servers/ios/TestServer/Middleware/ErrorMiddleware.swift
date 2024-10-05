//
//  ErrorMiddleware.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor
import CouchbaseLiteSwift

struct ErrorResponseFactory {
    private static func EncodeErrorResponse(request: Request, status: HTTPStatus, headers: HTTPHeaders, error: TestServerError) -> Response {
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
    
    public static func CreateErrorResponse(_ request: Request, _ error: TestServerError) -> Response {
        // Test server errors are 500 Internal, other errors are 400 Bad Request
        let status: HTTPStatus = error.domain == .TESTSERVER ? HTTPStatus(statusCode: error.code) : .badRequest
        let headers: HTTPHeaders = [:]
        
        return EncodeErrorResponse(request: request, status: status, headers: headers, error: error)
    }
    
    public static func UnknownErrorResponse(_ request: Request, _ nserror: NSError) -> Response {
        let error = TestServerError(domain: .TESTSERVER,
                                    code: 500,
                                    message: "Encountered unknown error: \(nserror.localizedDescription)")
        
        let status: HTTPStatus = .internalServerError
        let headers: HTTPHeaders = [:]
        
        request.logger.error(Logger.Message(stringLiteral: error.message))
        
        return EncodeErrorResponse(request: request, status: status, headers: headers, error: error)
    }
}

class TestServerErrorMiddleware : Middleware {
    public func respond(to request: Vapor.Request, chainingTo next: Vapor.Responder) -> NIOCore.EventLoopFuture<Vapor.Response> {
        next.respond(to: request).flatMapErrorThrowing { error in
            if let error = error as? TestServerError {
                return ErrorResponseFactory.CreateErrorResponse(request, error)
            } else {
                return ErrorResponseFactory.UnknownErrorResponse(request, error as NSError)
            }
            
        }
    }
}
