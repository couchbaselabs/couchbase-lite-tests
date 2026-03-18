//
//  MultipeerTransport.swift
//  TestServer
//

import Vapor
import CouchbaseLiteSwift

extension ContentTypes {
    enum MultipeerTransport: String, Content {
        case wifi = "WIFI"
        case bluetooth = "BLUETOOTH"
    }
}
extension ContentTypes.MultipeerTransport {
    init(transportType: CouchbaseLiteSwift.MultipeerTransport) {
        switch transportType {
        case .wifi:
            self = ContentTypes.MultipeerTransport.wifi
        case .bluetooth:
            self = ContentTypes.MultipeerTransport.bluetooth
        @unknown default:
            fatalError("Encountered unknown enum value from CouchbaseLiteSwift.MultipeerTransport")
        }
    }
}


