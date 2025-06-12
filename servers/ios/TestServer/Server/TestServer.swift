//
//  TestServer.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import os
import Vapor

class TestServer : ObservableObject {
    var app : Vapor.Application
    
    public static let maxAPIVersion = 1
    
    public static let serverID = UUID()
    
    init(port: Int) {
        do {
            var env : Environment = .development
            try LoggingSystem.bootstrap(from: &env)
            Log.initialize()
            
            let urls = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)
            let sessionManager = try SessionManager(filesDirectory: urls[0])
            
            app = Application(env)
            app.storage[SessionManagerKey.self] = sessionManager
            configure(port: port)
        } catch {
            fatalError(error.localizedDescription)
        }
    }
    
    public func run() async {
        defer { app.shutdown() }
        do {
            try await app.runFromAsyncMainEntrypoint()
        } catch {
            fatalError(error.localizedDescription)
        }
    }
    
    private func configure(port: Int) {
        app.http.server.configuration.hostname = "0.0.0.0"
        app.http.server.configuration.port = port
        
        Log.log(level: .info, message: "Configuring HTTP server with hostname: 0.0.0.0 and port: \(port)")
        
        // Use custom error middleware
        app.middleware = .init()
        app.middleware.use(TestServerMiddleware(app: app))
        app.middleware.use(TestServerErrorMiddleware())
        setupRoutes()
    }
    
    /// Implement API v1.0.0
    private func setupRoutes() {
        app.get("", use: Handlers.getRoot)
        app.post("newSession", use: Handlers.newSession)
        app.post("reset", use: Handlers.resetHandler)
        app.post("getAllDocuments", use: Handlers.getAllDocuments)
        app.post("getDocument", use: Handlers.getDocument)
        app.post("updateDatabase", use: Handlers.updateDatabase)
        app.post("snapshotDocuments", use: Handlers.snapshotDocuments)
        app.post("verifyDocuments", use: Handlers.verifyDocuments)
        app.post("startReplicator", use: Handlers.startReplicator)
        app.post("getReplicatorStatus", use: Handlers.getReplicatorStatus)
        app.post("performMaintenance", use: Handlers.performMaintenance)
        app.post("runQuery", use: Handlers.runQuery)
        
        Log.log(level: .debug, message: "Server configured with the following routes: \n\(app.routes.description)")
    }
}

private struct SessionManagerKey: StorageKey {
    typealias Value = SessionManager
}

extension Vapor.Application {
    var sessionManager : SessionManager {
        return self.storage.get(SessionManagerKey.self)!
    }
}

/// This extension is temporary and can be removed once Vapor gets this support.
private extension Vapor.Application {
    static let baseExecutionQueue = DispatchQueue(label: "vapor.codes.entrypoint", qos: .background)
    
    func runFromAsyncMainEntrypoint() async throws {
        try await withCheckedThrowingContinuation { continuation in
            Vapor.Application.baseExecutionQueue.async { [self] in
                do {
                    try self.run()
                    continuation.resume()
                } catch {
                    continuation.resume(throwing: error)
                }
            }
        }
    }
}
