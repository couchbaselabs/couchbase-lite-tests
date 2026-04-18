//
//  TLSIdentityData.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 6/4/25.
//

import Vapor

extension ContentTypes {
    enum IdentityDataEncoding : String, Codable {
        case PKCS12 = "PKCS12"
    }
    
    struct TLSIdentityData : Content {
        let encoding: IdentityDataEncoding
        let data: String
        let password: String?
    }
}
