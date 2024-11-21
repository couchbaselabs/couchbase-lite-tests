//
//  SessionManager.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/10/24.
//

import Foundation
import Vapor

struct Session {
    let id: String
    let databaseManager: DatabaseManager
    let sessionManager: SessionManager
}

class SessionManager {
    private let databaseManager: DatabaseManager
    
    private let queue = DispatchQueue(label: "SessionManager", attributes: .concurrent)
    
    private var sessions: [String: Session] = [:]
    
    init(databaseManager: DatabaseManager) {
        self.databaseManager = databaseManager
    }
    
    @discardableResult
    func createSession(id: String) throws -> Session {
        return try queue.sync(flags: .barrier) {
            if sessions[id] != nil {
                throw TestServerError.badRequest("Session '\(id)' already exists")
            }
            
            // We will only maintain one session at a time. This may change in the future
            sessions.removeAll()
            
            // Using shared Database manager at least for now.
            let session = Session(id: id, databaseManager: databaseManager, sessionManager: self)
            sessions[id] = session
            return session
        }
    }
    
    func createTempSession() -> Session {
        return Session(id: UUID().uuidString, databaseManager: databaseManager, sessionManager: self)
    }
    
    func getSession(id: String) throws -> Session {
        return try queue.sync {
            guard let session = sessions[id] else {
                throw TestServerError.badRequest("Session '\(id)' does not exist")
            }
            return session
        }
    }
}
