//
//  FileDownloader.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 6/11/25.
//

import Foundation

struct FileDownloader {
    static func download(url: URL, to path: String) throws {
        let destUrl = URL(fileURLWithPath: path)
                
        let sema = DispatchSemaphore(value: 0)
        var caughtError: Error?

        let config = URLSessionConfiguration.ephemeral
        let session = URLSession(configuration: config)
        let task = session.downloadTask(with: url) { location, response, err in
            defer {
                sema.signal()
            }
            
            if let err = err {
                caughtError = err
                return
            }
            
            guard let location = location else {
                caughtError = NSError(domain: NSURLErrorDomain, code: NSURLErrorUnknown,
                                      userInfo: [NSLocalizedDescriptionKey: "No file location returned"])
                return
            }
            
            do {
                try FileManager.default.moveItem(at: location, to: destUrl)
            } catch {
                caughtError = error
            }
        }
        
        task.resume()
        sema.wait()
        session.finishTasksAndInvalidate()
                    
        if let error = caughtError {
            throw error
        }
    }
}
