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
    func writeLog(level: LogLevel, domain: String, message: String)
    func close()
}

public class Log {
    private static let sConsoleLogger = ConsoleLogger()
    private static var sLogger: LoggerProtocol = sConsoleLogger
    private static let sLogQueue = DispatchQueue(label: "com.couchbase.log.LogQueue")
    
    private init () { }
    
    public static func initialize() {
        let logSink = CustomLogger()
        LogSinks.custom = CustomLogSink(level: .verbose, logSink: logSink)
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
        sLogQueue.async {
            sLogger.writeLog(level: level, domain: "TS", message: message)
        }
    }
    
    public static func logToConsole(level: LogLevel,  message: String) {
        sConsoleLogger.writeLog(level: level, domain: "TS", message: message)
    }
    
    fileprivate static func writeLog(level: LogLevel, domain: LogDomain, message: String) {
        sLogQueue.async {
            sLogger.writeLog(level: level, domain: domain.name, message: message)
        }
    }
}

private class CustomLogger : LogSinkProtocol {
    var lines: [String] = []
    private let queue = DispatchQueue(label: "CustomLogger.lines.queue")
    
    func writeLog(level: LogLevel, domain: LogDomain, message: String) {
        queue.async {
            self.lines.append(message)
        }
    }
}

private class ConsoleLogger: LoggerProtocol {
    let logger = os.Logger()
    
    func writeLog(level: LogLevel, domain: String, message: String) {
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
    
    public func writeLog(level: LogLevel, domain: String, message: String) {
        lock.lock()
        defer { lock.unlock() }
        
        let msg = "[\(level.osLogType)] \(domain): \(message)"
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
        default: return .info
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
        default: return self.rawValue == 16 ? "listener" : "database"
        }
    }
}
