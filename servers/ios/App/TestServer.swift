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
    let dbConnection : DatabaseManager
    public static let logger : os.Logger = os.Logger()
    
    public static let maxAPIVersion = 1
    public static let serverID = UUID()
    
    init(port: Int, dbManager: DatabaseManager) {
        self.dbConnection = dbManager
        do {
            var env : Environment = .development
            try LoggingSystem.bootstrap(from: &env)
            
            app = Application(env)
            configure(app, port)
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
    
    private func configure(_ app: Application, _ port: Int) {
        app.http.server.configuration.hostname = "0.0.0.0"
        app.http.server.configuration.port = port
        
        TestServer.logger.log(level: .info, "Configuring HTTP server with hostname: 0.0.0.0 and port: \(port)")
        
        // Use custom error middleware
        app.middleware = .init()
        app.middleware.use(HeadersMiddleware())
        app.middleware.use(TestServerErrorMiddleware())

        setupRoutes(app)
    }
    
    private func setupRoutes(_ app: Application) {
        app.get("", use: Handlers.getRoot)
        app.post("reset", use: Handlers.resetHandler)
        app.post("getAllDocuments", use: Handlers.getAllDocuments)
        app.post("updateDatabase", use: Handlers.updateDatabase)
        app.post("snapshotDocuments", use: Handlers.snapshotDocuments)
        app.post("verifyDocuments", use: Handlers.verifyDocuments)
        app.post("startReplicator", use: Handlers.startReplicator)
        app.post("getReplicatorStatus", use: Handlers.getReplicatorStatus)
        app.post("performMaintenance", use: Handlers.performMaintenance)
        
        TestServer.logger.log(level: .debug, "Server configured with the following routes: \n\(app.routes.description)")
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
