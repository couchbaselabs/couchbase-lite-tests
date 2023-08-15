import Foundation
import Network

@main
public struct TestServerFinder {
    let browser: NWBrowser
    
    let queue = DispatchQueue(label: "TestServerFinderQueue", target: .global())
       
    init() {
        browser = NWBrowser(for: .bonjour(type: "_testserver._tcp", domain: nil), using: NWParameters())
    }
    
    enum BrowsingError: Error {
        case Timeout
    }
    
    func start(timeout: TimeInterval = 30) async throws -> String {
        return try await withCheckedThrowingContinuation { cont in
            var result: String?
            
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
                    if let r = result {
                        cont.resume(returning: r)
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
                    case .added(let r):
                        if case .service(let name, _, _, _) = r.endpoint {
                            result = name
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
