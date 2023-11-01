//
//  ServerInfo.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor
import UIKit
import CouchbaseLiteSwift

extension ContentTypes {
    struct DeviceInfo : Codable {
        let model: String?
        let systemName: String
        let systemVersion: String
        let systemApiVersion: String?
    }
    struct ServerInfo : Content {
        let version: String
        let apiVersion: Int
        let cbl: String
        let device: DeviceInfo
        let additionalInfo: String?
        
        init() {
            self.version = CBLVersion.version
            self.apiVersion = TestServer.maxAPIVersion
            self.cbl = "couchbase-lite-swift"
            self.device = DeviceInfo(model: UIDevice.current.name, systemName: UIDevice.current.systemName, systemVersion: UIDevice.current.systemVersion, systemApiVersion: nil)
            self.additionalInfo = nil
        }
    }
}
