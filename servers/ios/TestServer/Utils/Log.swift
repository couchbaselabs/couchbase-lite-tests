//
//  Logger.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 11/17/24.
//

import Foundation
import os
import CouchbaseLiteSwift

public protocol LoggerProtocol : LogSinkProtocol {
    func writeLog(level: LogLevel, domain: String, message: String)
    
    func close()
}

public class Log {
    private static let sConsoleLogger = ConsoleLogger()
    private static var currentLogger: LoggerProtocol?
    private static let sLogQueue = DispatchQueue(label: "com.couchbase.log.LogQueue")
    
    private init () { }
    
    public static func initialize() {
        useConsoleLogger()
    }
    
    public static func useRemoteLogger(_ remoteLogger: RemoteLogger) {
        updateLogger(remoteLogger)
    }
    
    public static func useConsoleLogger() {
        updateLogger(sConsoleLogger)
    }
    
    private static func updateLogger(_ logger: LoggerProtocol?) {
        sLogQueue.sync {
            currentLogger?.close()
            currentLogger = logger
            
            if let logSink = currentLogger {
                LogSinks.custom = CustomLogSink(level: .verbose, logSink: logSink)
            } else {
                LogSinks.custom = nil
            }
        }
    }
    
    public static func logToConsole(level: LogLevel, message: String) {
        sConsoleLogger.writeLog(level: level, domain: "TS", message: message)
    }
    
    public static func log(level: LogLevel, message: String) {
        sLogQueue.sync {
            currentLogger?.writeLog(level: level, domain: "TS", message: message)
        }
    }
    
    fileprivate static func shouldFilter(level: LogLevel, message: String) -> Bool {
#if !INCLUDE_DEBUG
        if (level == .debug) {
            return true
        }
#endif
        
        if (message.contains("mbedTLS(S)")) {
            return true;
        }
        
        return false
    }
}

private class ConsoleLogger : LoggerProtocol {
    let logger = os.Logger()

    func writeLog(level: LogLevel, domain: LogDomain, message: String) {
        writeLog(level: level, domain: domain.name, message: message)
    }
    
    func writeLog(level: LogLevel, domain: String, message: String) {
        if (Log.shouldFilter(level: level, message: message)) {
            return
        }
        logger.log(level: level.osLogType, "[\(domain)] \(message)")
    }
    
    func close() { }
}

public class RemoteLogger: LoggerProtocol {
    private let url: URL
    private let headers: Dictionary<String, String>?
    
    private var webSocketTask: URLSessionWebSocketTask?
    private var session: URLSession
    
    private let queue = DispatchQueue(label: "com.couchbase.log.RemoteLogger")
    
    init(url: URL, headers: Dictionary<String, String>?) {
        self.url = url
        self.headers = headers
        self.session = URLSession(configuration: .default)
    }
    
    deinit {
        close()
    }
    
    public func connect(timeout: TimeInterval) throws {
        var errorToThrow: Error?
        queue.sync {
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
                self.doClose()
                errorToThrow = TestServerError.badRequest("RemoteLogger: Timeout connecting to \(url.absoluteString)")
            }
            
            if let error = connError {
                self.doClose()
                errorToThrow = TestServerError.badRequest("RemoteLogger: Error connecting to \(url.absoluteString) : \(error)")
            }
        }
        
        if let error = errorToThrow {
            throw error
        }
    }
    
    public func writeLog(level: LogLevel, domain: LogDomain, message: String) {
        writeLog(level: level, domain: domain.name, message: message)
    }
    
    public func writeLog(level: LogLevel, domain: String, message: String) {
        queue.async { [weak self] in
            guard let self = self else {
                return
            }
            
            if (Log.shouldFilter(level: level, message: message)) {
                return
            }
            
            let msg = "[\(level.name)] \(domain): \(message)"
            self.webSocketTask?.send(URLSessionWebSocketTask.Message.string(msg)) { error in
                if let error = error {
                    Log.logToConsole(level: .error, message: "RemoteLogger: Cannot Send Log Message: \(error)")
                }
            }
        }
    }

    public func close() {
        queue.sync {
            doClose()
        }
    }
    
    private func doClose() {
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
    
    var name: String {
        switch self {
        case .debug: return "DEBUG"
        case .verbose: return "VERBOSE"
        case .info: return "INFO"
        case .warning: return "WARNING"
        case .error: return "ERROR"
        case .none: return "NONE"
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
