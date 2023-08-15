import Foundation
import Network

@main
public struct TestServerFinder {
    let browser: NWBrowser
    
    let queue = DispatchQueue(label: "TestServerFinderQueue", target: .global())
       
    init() {
        browser = NWBrowser(for: .bonjour(type: "_TestServerIPAddress._tcp", domain: nil), using: NWParameters())
    }
    
    enum BrowsingError: Error {
        case Timeout
    }
    
    func start(timeout: TimeInterval = 30) async throws -> String {
        return try await withCheckedThrowingContinuation { cont in
            var result: (String?, Error?)
            
            let timeoutTask = Task {
                try await Task.sleep(nanoseconds: UInt64(timeout) * NSEC_PER_SEC)
                browser.cancel()
            }
            
            browser.stateUpdateHandler = { newState in
                switch newState {
                case .failed(let error):
                    timeoutTask.cancel()
                    cont.resume(throwing: error)
                case .cancelled:
                    timeoutTask.cancel()
                    if let result = result.0 {
                        cont.resume(returning: result)
                    } else if let err = result.1 {
                        cont.resume(throwing: err)
                    } else {
                        cont.resume(throwing: BrowsingError.Timeout)
                    }
                default:
                    break
                }
            }
            
            browser.browseResultsChangedHandler = { results, changes in
                for change in changes {
                    switch change {
                    case .added(let res):
                        let params = NWParameters(tls: nil, tcp: NWProtocolTCP.Options())
                        let connection = NWConnection(to: res.endpoint, using: params)
                        connection.start(queue: self.queue)
                        
                        connection.receive(minimumIncompleteLength: 1, maximumLength: Int.max) {
                            content, contentContext, isComplete, error in
                            if let data = content {
                                result = (String(data: data, encoding: .utf8), nil)
                            } else if let err = error {
                                result = (nil, err)
                            }
                            browser.cancel()
                        }
                    default:
                        break
                    }
                }
            }
            browser.start(queue: self.queue)
        }
    }

    public static func main() async throws {
        let ipAddress = try await TestServerFinder().start()
        print("\(ipAddress)")
    }
}
