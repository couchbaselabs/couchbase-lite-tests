import Foundation
import Network

/// Start a bonjour service listener  with type = "_testserver._tcp" and name = en0's IP address with '-' instead of '.'.
/// Clients can just check the service name to obtain the IP Address information. The service will just do nothing
/// and will end the connection when a client connects to the service.
public class IPAddress {
    public static let shared = IPAddress()
    
    let serviceType = "_testserver._tcp"
    let address: String
    let serviceName: String
    let listener: NWListener
    
    private let queue = DispatchQueue(label: "IPAddressQueue", target: .global())
    
    private init() {
        guard let address = IPAddress.getIPAddress() else {
            fatalError("Failed to get IP Address")
        }
        self.address = address
        self.serviceName = self.address.replacingOccurrences(of: ".", with: "-")
        self.listener = try! NWListener(using: NWParameters(tls: nil, tcp: NWProtocolTCP.Options()))
        self.listener.service = NWListener.Service(name: self.serviceName, type: serviceType);
        self.listener.newConnectionHandler = { conn in
            conn.cancel() // do nothing
        }
        listener.stateUpdateHandler = { newState in
            switch newState {
            case .ready:
                NSLog("IPAddress Server (\(self.address)) started ...")
            case .failed(let error):
                NSLog("IPAddress Server (\(self.address)) failed to start : \(error)")
            case .cancelled:
                NSLog("IPAddress Server (\(self.address)) stopped ...")
            default:
                break
            }
        }
    }
    
    public func advertise() {
        listener.start(queue: queue)
    }
    
    public func stop() {
        listener.cancel()
    }
    
    private static func getIPAddress() -> String? {
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
