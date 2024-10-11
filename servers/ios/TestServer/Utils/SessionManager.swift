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
}

struct SessionKey: StorageKey {
    typealias Value = Session
}

class SessionManager {
    static let shared = SessionManager()
    
    private let queue = DispatchQueue(label: "SessionManager", attributes: .concurrent)
    
    private var sessions: [String: Session] = [:]
    
    private init() { }
    
    func createSession(id: String, databaseManager: DatabaseManager) throws -> Session {
        return try queue.sync(flags: .barrier) {
            if sessions[id] != nil {
                throw TestServerError.badRequest("Session '\(id)' already exists")
            }
            
            // We will only maintain one session at a time. This may change in the future
            sessions.removeAll()
            
            let session = Session(id: id, databaseManager: databaseManager)
            sessions[id] = session
            return session
        }
    }
    
    func createTempSession(databaseManager: DatabaseManager) -> Session {
        return Session(id: UUID().uuidString, databaseManager: databaseManager)
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
