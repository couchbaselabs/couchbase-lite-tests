import Foundation

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
