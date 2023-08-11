//
//  ReplicatorConfiguration.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor

extension ContentTypes {
    enum ReplicatorType : String, Codable {
        case push = "push"
        case pull = "pull"
        case pushpull = "pushAndPull"
    }
    struct ReplicatorConfiguration : Codable {
        let database: String
        let collections: [ReplicationCollection]
        let endpoint: String
        let replicatorType: ReplicatorType
        let continuous: Bool
        let authenticator: ReplicatorAuthenticator
        let enableDocumentListener: Bool
        
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            database = try container.decode(String.self, forKey: .database)
            collections = try container.decode([ReplicationCollection].self, forKey: .collections)
            endpoint = try container.decode(String.self, forKey: .endpoint)
            replicatorType = try container.decode(ReplicatorType.self, forKey: .replicatorType)
            continuous = try container.decode(Bool.self, forKey: .continuous)
            enableDocumentListener = try container.decode(Bool.self, forKey: .enableDocumentListener)

            // Decode the 'type' field from the 'authenticator' container to determine the authenticator type
            let authContainer = try container.nestedContainer(keyedBy: AuthenticatorCodingKeys.self, forKey: .authenticator)
            let authType = try authContainer.decode(AuthenticatorType.self, forKey: .type)
            switch authType {
            case .BASIC:
                authenticator = try container.decode(ReplicatorBasicAuthenticator.self, forKey: .authenticator)
            case .SESSION:
                authenticator = try container.decode(ReplicatorSessionAuthenticator.self, forKey: .authenticator)
            }
        }

        func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(database, forKey: .database)
            try container.encode(collections, forKey: .collections)
            try container.encode(endpoint, forKey: .endpoint)
            try container.encode(replicatorType, forKey: .replicatorType)
            try container.encode(continuous, forKey: .continuous)
            try container.encode(enableDocumentListener, forKey: .enableDocumentListener)

            // Encode the `authenticator` property
            switch authenticator {
            case let basicAuth as ReplicatorBasicAuthenticator:
                try container.encode(basicAuth, forKey: .authenticator)
            case let sessionAuth as ReplicatorSessionAuthenticator:
                try container.encode(sessionAuth, forKey: .authenticator)
            default:
                throw EncodingError.invalidValue(authenticator, EncodingError.Context(codingPath: [CodingKeys.authenticator], debugDescription: "Invalid authenticator type"))
            }
        }

        private enum CodingKeys: String, CodingKey {
            case database
            case collections
            case endpoint
            case replicatorType
            case continuous
            case authenticator
            case enableDocumentListener
        }
        
        private enum AuthenticatorCodingKeys: String, CodingKey {
            case type
        }
    }
}
