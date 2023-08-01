//
//  TestServer.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import Vapor

class TestServer : ObservableObject {
    var app : Vapor.Application
    let dbConnection : DatabaseManager
    
    init(port: Int, dbManager: DatabaseManager) {
        self.dbConnection = dbManager
        do {
            var env = try Environment.detect()
            try LoggingSystem.bootstrap(from: &env)
            
            app = Application(env)
            try configure(app, port)
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
    
    private func configure(_ app: Application, _ port: Int) throws {
        // uncomment to serve files from /Public folder
        // app.middleware.use(FileMiddleware(publicDirectory: app.directory.publicDirectory))
        
        app.http.server.configuration.hostname = "0.0.0.0"
        app.http.server.configuration.port = port

        Task {
            try await routes(app)
        }
        // register routes
    }
    
    private func routes(_ app: Application) async throws {
        app.get { req async in
            "It works!"
        }
        
        app.post("reset") { [self] req async in
            dbConnection.reset()
            return "Reset"
        }
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
