//
//  TestServerMiddleware.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 09/08/2023.
//

import Foundation
import Vapor

struct SessionKey: StorageKey {
    typealias Value = Session
}

class TestServerMiddleware : AsyncMiddleware {
    let kHeaderKeyServerID = "CBLTest-Server-ID"
    let kHeaderKeyClientID = "CBLTest-Client-ID"
    let kHeaderKeyAPIVersion = "CBLTest-API-Version"
    let kHeaderKeyContentType = "content-type"
    let defaultContentType = "application/json"
    
    private let application: Application
    
    init(app: Application) {
        self.application = app
    }
    
    func respond(to request: Vapor.Request, chainingTo next: Vapor.AsyncResponder) async throws -> Vapor.Response {
        Log.log(level: .debug, message: "Received request: \(request.description)")
        
        let isGetRoot = request.route?.description == "GET /"
        
        let version = isGetRoot ? 0 : try getAndVerifyVersion(request.headers)
        
        var session: Session
        do {
            if isGetRoot || request.route?.description == "POST /newSession" {
                session = createNewTempSession()
            } else {
                session = try getSession(clientID: getClientID(request.headers))
            }
            request.storage[SessionKey.self] = session
        } catch(let error as TestServerError) {
            // This middleware sits before the error middleware,
            // so we have to create this error ourselves
            Log.log(level: .error, message: "Request failed with error: \(error)")
            let response = ErrorResponseFactory.CreateErrorResponse(request, error)
            return withResponseHeaders(response, version: version)
        }
        
        request.headers.contentType = .json
        
        let response = try await next.respond(to: request)
        let responseWithHeaders = withResponseHeaders(response, version: version)
        
        Log.log(level: .debug, message: "Responding with response: \n\(responseWithHeaders)")
        return responseWithHeaders
    }
    
    func withResponseHeaders(_ response: Response, version: Int) -> Response {
        let resolvedVersion = version != 0 ? version : TestServer.maxAPIVersion
        response.headers.add(name: kHeaderKeyServerID, value: TestServer.serverID.uuidString)
        response.headers.add(name: kHeaderKeyAPIVersion, value: "\(resolvedVersion)")
        
        // Python Test client requires content-type:
        if (!response.headers.contains(name: kHeaderKeyContentType)) {
            response.headers.add(name: kHeaderKeyContentType, value: defaultContentType)
        }
        return response
    }
    
    private func getAndVerifyVersion(_ headers: HTTPHeaders) throws -> Int {
        guard let versionStr = headers.first(name: kHeaderKeyAPIVersion),
              let version = Int(versionStr) else {
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "Missing CBLTest-API-Version headers")
        }
        if version > TestServer.maxAPIVersion {
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "The API version specified is not supported.")
        }
        return version
    }
    
    func getClientID(_ headers: HTTPHeaders) throws -> String {
        guard let id = headers.first(name: kHeaderKeyClientID) else {
            throw TestServerError(domain: .TESTSERVER, code: 400, message: "Missing CBLTest-Client-ID headers")
        }
        return id
    }
    
    private func createNewTempSession() -> Session {
        return application.sessionManager.createTempSession()
    }
    
    private func getSession(clientID: String) throws -> Session {
        return try application.sessionManager.getSession(id: clientID)
    }
}

extension Vapor.Request {
    var session : Session {
        guard let s = self.storage.get(SessionKey.self) else {
            fatalError("No session found in request")
        }
        return s
    }
    
    var databaseManager : DatabaseManager {
        guard let manager = self.session.databaseManager else {
            fatalError("Get database manager from temp session is not supported")
        }
        return manager
    }
}
