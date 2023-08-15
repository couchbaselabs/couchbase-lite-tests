import Foundation
import Network

public class IPAddressServer {
    let address: String
    let listener: NWListener
    let queue = DispatchQueue(label: "IPAddressServerQueue", target: .global())
    
    public init() {
        guard let address = IPAddress.address() else {
            fatalError("Failed to get IP Address")
        }
        self.address = address
        self.listener = try! NWListener(using: NWParameters(tls: nil, tcp: NWProtocolTCP.Options()))
        self.listener.service = NWListener.Service(name: self.address, type: "_TestServerIPAddress._tcp");
    }
    
    public func start() {
        listener.stateUpdateHandler = { newState in
            switch newState {
            case .ready:
                TSLogger.info("IPAddress Server (\(self.address)) started ...")
            case .failed(let error):
                TSLogger.error("IPAddress Server (\(self.address)) failed to start : \(error)")
            case .cancelled:
                TSLogger.info("IPAddress Server (\(self.address)) stopped ...")
            default:
                break
            }
        }
        
        listener.newConnectionHandler = { conn in
            TSLogger.info("IPAddress Server (\(self.address)) receiving a connection ...")
            conn.start(queue: self.queue)
            let data = self.address.data(using: .utf8)
            conn.send(content: data, contentContext: .defaultMessage, isComplete: true, completion: .idempotent)
        }
        listener.start(queue: .main)
    }
}

public class IPAddress {
    class func address() -> String? {
        var ifaddr: UnsafeMutablePointer<ifaddrs>? = nil
        if getifaddrs(&ifaddr) == 0 {
            var current = ifaddr
            while current != nil {
                let interface = current!.pointee
                let family = interface.ifa_addr.pointee.sa_family
                if family == UInt8(AF_INET) {
                    let name = String(cString: interface.ifa_name)
                    if name == "en0" {
                        var address = [CChar](repeating: 0, count: Int(NI_MAXHOST))
                        getnameinfo(interface.ifa_addr, socklen_t((interface.ifa_addr.pointee.sa_len)), &address, socklen_t(address.count), nil, socklen_t(0), NI_NUMERICHOST)
                        return String(cString: address)
                    }
                }
                current = current!.pointee.ifa_next
            }
            freeifaddrs(ifaddr)
        }
        return nil
    }
}
