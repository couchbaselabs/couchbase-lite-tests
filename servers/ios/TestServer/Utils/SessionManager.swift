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
    let databaseManager: DatabaseManager?
    let sessionManager: SessionManager
}

class SessionManager {
    private let fileDirectory: URL
    
    private let queue = DispatchQueue(label: "SessionManager", attributes: .concurrent)
    
    private var sessions: [String: Session] = [:]
    
    private var sessionsDirectory: URL {
        return fileDirectory.appendingPathComponent("sessions")
    }
    
    init(filesDirectory: URL) throws {
        self.fileDirectory = filesDirectory
        try resetSessionsDirectory()
    }
    
    @discardableResult
    func createSession(id: String, datasetVersion: String) throws -> Session {
        return try queue.sync(flags: .barrier) {
            if sessions[id] != nil {
                throw TestServerError.badRequest("Session '\(id)' already exists")
            }
            
            // We will only maintain one session at a time. This may change in the future
            sessions.removeAll()
            
            let dir = try createSessionDirectory(for: id)
            let manager = DatabaseManager(directory: dir.path(), datasetVersion: datasetVersion)
            
            // Using shared Database manager at least for now.
            let session = Session(id: id, databaseManager: manager, sessionManager: self)
            sessions[id] = session
            return session
        }
    }
    
    func createTempSession() -> Session {
        return Session(id: UUID().uuidString, databaseManager: nil, sessionManager: self)
    }
    
    func getSession(id: String) throws -> Session {
        return try queue.sync {
            guard let session = sessions[id] else {
                throw TestServerError.badRequest("Session '\(id)' does not exist")
            }
            return session
        }
    }
    
    private func resetSessionsDirectory() throws {
        let fileManager = FileManager.default
        let dir = sessionsDirectory
        if fileManager.fileExists(atPath: dir.path) {
            try fileManager.removeItem(at: dir)
        }
        try fileManager.createDirectory(at: dir, withIntermediateDirectories: true, attributes: nil)
    }
    
    private func createSessionDirectory(for id: String) throws -> URL {
        let dir = sessionsDirectory.appendingPathComponent(id)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true, attributes: nil)
        return dir
    }
}
