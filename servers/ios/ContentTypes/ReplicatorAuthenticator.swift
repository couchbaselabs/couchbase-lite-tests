//
//  ReplicatorBasicAuthenticator.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor

protocol ReplicatorAuthenticator: Codable {
    var type: ContentTypes.AuthenticatorType { get }
}

extension ContentTypes {
    enum AuthenticatorType : String, Codable {
        case BASIC = "BASIC"
        case SESSION = "SESSION"
    }
    struct ReplicatorBasicAuthenticator : ReplicatorAuthenticator, Codable {
        let type: AuthenticatorType
        let username: String
        let password: String
    }
    struct ReplicatorSessionAuthenticator : ReplicatorAuthenticator, Codable {
        let type: AuthenticatorType
        let sessionID: String
        let cookieName: String
    }
}
