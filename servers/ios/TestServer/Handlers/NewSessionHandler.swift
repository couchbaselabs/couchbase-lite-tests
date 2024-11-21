//
//  NewSessionHandler.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/11/24.
//

import Vapor

extension Handlers {
    static let newSession: EndpointHandlerEmptyResponse = { req throws in
        guard let newSession = try? req.content.decode(ContentTypes.NewSession.self) else {
            throw TestServerError.badRequest("Request body does not match the 'NewSession' scheme.")
        }
        
        let session = try req.application.sessionManager.createSession(id: newSession.id)
        Log.logToConsole(level: .info, message: "Start new session with id : \(session.id)");
        
        if let logging = newSession.logging {
            guard let url = URL(string: "ws://\(logging.url)/openLogStream") else {
                throw TestServerError.badRequest("Invalid remote logger URL : \(logging.url)")
            }
            Log.logToConsole(level: .info, message: "Use remote logger '\(url.absoluteString)' with log-id '\(session.id)' and tag '\(logging.tag)'");
            
            let headers = [
                "CBL-Log-ID": session.id,
                "CBL-Log-Tag": logging.tag
            ]
            
            let remoteLogger = RemoteLogger(url: url, headers: headers)
            try remoteLogger.connect(timeout: 10)
            Log.useCustomLogger(remoteLogger)
        } else {
            Log.useDefaultLogger()
        }
        
        return Response(status: .ok)
    }
}
