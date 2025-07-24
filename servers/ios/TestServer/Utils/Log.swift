//
//  Logger.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 11/17/24.
//

import Foundation
import os
import CouchbaseLiteSwift

public protocol LoggerProtocol {
    func log(level: LogLevel, domain: String, message: String)
    func close()
}

public class Log {
    private static let sConsoleLogger = ConsoleLogger()
    private static var sLogger: LoggerProtocol = sConsoleLogger
    private static let sLogQueue = DispatchQueue(label: "com.couchbase.log.LogQueue")
    
    private init () { }
    
    public static func initialize() {
        Database.log.custom = CBLLogger(level: .verbose)
    }
        
    public static func useDefaultLogger() {
        sLogQueue.sync {
            sLogger.close()
            sLogger = sConsoleLogger
        }
    }
    
    public static func useCustomLogger(_ logger: LoggerProtocol) {
        sLogQueue.sync {
            sLogger.close()
            sLogger = logger
        }
    }
    
    public static func log(level: LogLevel, message: String) {
        if(shouldFilter(level: level, domain: nil, message: message)) {
            return
        }
        
        sLogQueue.async {
            sLogger.log(level: level, domain: "TS", message: message)
        }
    }
    
    public static func logToConsole(level: LogLevel,  message: String) {
        if(shouldFilter(level: level, domain: nil, message: message)) {
            return
        }
        
        sConsoleLogger.log(level: level, domain: "TS", message: message)
    }
    
    fileprivate static func log(level: LogLevel, domain: LogDomain, message: String) {
        if(shouldFilter(level: level, domain: domain, message: message)) {
            return
        }
        
        sLogQueue.async {
            sLogger.log(level: level, domain: domain.name, message: message)
        }
    }
    
    private static func shouldFilter(level: LogLevel, domain: LogDomain?, message: String) -> Bool {
        #if !INCLUDE_DEBUG
        if(level == .debug) {
            return true
        }
        #endif
        
        if(message.contains("mbedTLS(S)")) {
            return true;
        }
        
        return false
    }
}

private class CBLLogger : CouchbaseLiteSwift.Logger {
    let level: LogLevel
    
    init(level: LogLevel) {
        self.level = level
    }
    
    func log(level: CouchbaseLiteSwift.LogLevel, domain: LogDomain, message: String) {
        Log.log(level: level, domain: domain, message: message)
    }
}

private class ConsoleLogger: LoggerProtocol {
    let logger = os.Logger()
    
    func log(level: LogLevel, domain: String, message: String) {
        logger.log(level: level.osLogType, "[\(domain)] \(message)")
    }

    func close() { }
}

public class RemoteLogger: LoggerProtocol {
    private let url: URL
    private let headers: Dictionary<String, String>?
    
    private var webSocketTask: URLSessionWebSocketTask?
    private var session: URLSession
    private let lock = NSLock()
    
    init(url: URL, headers: Dictionary<String, String>?) {
        self.url = url
        self.headers = headers
        self.session = URLSession(configuration: .default)
    }
    
    deinit {
        close()
    }
    
    public func connect(timeout: TimeInterval) throws {
        lock.lock()
        defer { lock.unlock() }
        
        if (webSocketTask != nil) {
            return
        }
        
        var request = URLRequest(url: url)
        
        headers?.forEach { key, value in
            request.setValue(value, forHTTPHeaderField: key)
        }
        
        let connSem = DispatchSemaphore(value: 0)
        var connError: Error?
        
        webSocketTask = session.webSocketTask(with: request)
        webSocketTask?.resume()
        webSocketTask?.sendPing { error in
            if let error = error {
                connError = error
            }
            connSem.signal()
        }
        
        let result = connSem.wait(timeout: .now() + timeout)
        if result == .timedOut {
            self.close()
            throw TestServerError.badRequest("RemoteLogger: Timeout connecting to \(url.absoluteString)")
        }
        
        if let error = connError {
            self.close()
            throw TestServerError.badRequest("RemoteLogger: Error connecting to \(url.absoluteString) : \(error)")
        }
    }
    
    public func log(level: LogLevel, domain: String, message: String) {
        lock.lock()
        defer { lock.unlock() }
        
        let msg = "[\(level.osLogType.stringValue)] \(domain): \(message)"
        webSocketTask?.send(URLSessionWebSocketTask.Message.string(msg)) { error in
            if let error = error {
                Log.logToConsole(level: .error, message: "RemoteLogger: Cannot Send Log Message: \(error)")
            }
        }
    }

    public func close() {
        lock.lock()
        defer { lock.unlock() }
        
        webSocketTask?.cancel(with: .normalClosure, reason: nil)
        webSocketTask = nil
    }
}

extension LogLevel {
    var osLogType: OSLogType {
        switch self {
        case .debug: return .debug
        case .verbose: return .info
        case .info: return .info
        case .warning: return .error
        case .error: return .error
        case .none:
            fatalError(".none is not convertible to an OSLogType.")
        @unknown default:
            fatalError("Unknown LogLevel case: \(self). Please add explicit handling for this case.")
        }
    }
}

extension LogDomain {
    var name: String {
        switch self {
        case .database: return "database"
        case .query: return "query"
        case .replicator: return "replicator"
        case .network: return "network"
        case .listener: return "listener"
        case .peerDiscovery: return "discovery"
        case .multipeer: return "multipeer"
        @unknown default:
            fatalError("Unknown LogDomain case : \(self). Please add explicit handling for this case.")
        }
    }
}

extension OSLogType {
    var stringValue: String {
        switch self {
        case .debug: return "DEBUG"
        case .info: return "INFO"
        case .default: return "DEFAULT"
        case .error: return "ERROR"
        case .fault: return "FAULT"
        default: return "UNKNOWN"
        }
    }
}
