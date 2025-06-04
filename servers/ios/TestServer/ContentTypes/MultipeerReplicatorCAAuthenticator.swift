//
//  MultipeerReplicatorCAAuthenticator.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 6/4/25.
//

import Vapor

extension ContentTypes {
    enum MultipeerReplicatorCAAuthenticatorType : String, Codable {
        case CACERT = "CA-CERT"
    }
    
    struct MultipeerReplicatorCAAuthenticator : Content {
        let type: MultipeerReplicatorCAAuthenticatorType
        let certificate: String
    }
}

