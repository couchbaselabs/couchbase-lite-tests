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
