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
        let authenticator: ReplicatorAuthenticator?
        let pinnedServerCert: String?
        let enableDocumentListener: Bool
        let enableAutoPurge: Bool
        
        public var description: String {
            var result: String = "ReplicatorConfiguration\n"
            result += "\tdatabase: \(database)\n"
            result += "\tendpoint: \(endpoint)\n"
            result += "\tcollections:\n"
            
            for replColl in collections {
                result += "\t\t\(replColl.names.description)\n"
                if let channels = replColl.channels {
                    result += "\t\tchannels: \(channels.description)\n"
                }
                if let docIDs = replColl.documentIDs {
                    result += "\t\tdocumentIDs: \(docIDs.description)\n"
                }
                if let pushFilter = replColl.pushFilter {
                    result += "\t\tpushFilter: \(pushFilter.name)\n"
                }
                if let pullFilter = replColl.pullFilter {
                    result += "\t\tpullFilter: \(pullFilter.name)\n"
                }
                if let conflictResolver = replColl.conflictResolver {
                    result += "\t\tconflictResolver: \(conflictResolver.name)\n"
                }
            }
            
            result += "\treplicatorType: \(replicatorType.rawValue)\n"
            result += "\tcontinuous: \(continuous.description)\n"
            
            if let auth = authenticator {
                result += "\tauthenticatorType: \(auth.type.rawValue)\n"
            }
            
            result += "\tpinnedServerCert: \(pinnedServerCert != nil ? "true" : "false")\n"
            result += "\tenableDocumentListener: \(enableDocumentListener.description)\n"
            result += "\tenableAutoPeruge: \(enableAutoPurge.description)\n"
            
            return result
        }
        
        init(from decoder: Decoder) throws {
            let container = try decoder.container(keyedBy: CodingKeys.self)
            database = try container.decode(String.self, forKey: .database)
            collections = try container.decode([ReplicationCollection].self, forKey: .collections)
            endpoint = try container.decode(String.self, forKey: .endpoint)
            replicatorType = try container.decodeIfPresent(ReplicatorType.self, forKey: .replicatorType) ?? .pushpull
            continuous = try container.decodeIfPresent(Bool.self, forKey: .continuous) ?? false
            enableDocumentListener = try container.decodeIfPresent(Bool.self, forKey: .enableDocumentListener) ?? false
            enableAutoPurge = try container.decodeIfPresent(Bool.self, forKey: .enableAutoPurge) ?? true
            
            if container.contains(.authenticator) {
                let authContainer = try container.nestedContainer(keyedBy: AuthenticatorCodingKeys.self, forKey: .authenticator)
                let authType = try authContainer.decode(AuthenticatorType.self, forKey: .type)
                switch authType {
                case .BASIC:
                    authenticator = try container.decode(ReplicatorBasicAuthenticator.self, forKey: .authenticator)
                case .SESSION:
                    authenticator = try container.decode(ReplicatorSessionAuthenticator.self, forKey: .authenticator)
                }
            } else {
                authenticator = nil
            }
            
            pinnedServerCert = try container.decodeIfPresent(String.self, forKey: .pinnedServerCert)
        }

        func encode(to encoder: Encoder) throws {
            var container = encoder.container(keyedBy: CodingKeys.self)
            try container.encode(database, forKey: .database)
            try container.encode(collections, forKey: .collections)
            try container.encode(endpoint, forKey: .endpoint)
            try container.encode(replicatorType, forKey: .replicatorType)
            try container.encode(continuous, forKey: .continuous)
            try container.encode(enableDocumentListener, forKey: .enableDocumentListener)
            try container.encode(enableAutoPurge, forKey: .enableAutoPurge)

            // Encode the `authenticator` property
            if let auth = authenticator {
                switch auth {
                case let basicAuth as ReplicatorBasicAuthenticator:
                    try container.encode(basicAuth, forKey: .authenticator)
                case let sessionAuth as ReplicatorSessionAuthenticator:
                    try container.encode(sessionAuth, forKey: .authenticator)
                default:
                    throw EncodingError.invalidValue(auth, EncodingError.Context(codingPath: [CodingKeys.authenticator], debugDescription: "Invalid authenticator type"))
                }
            }
            
            try container.encodeIfPresent(pinnedServerCert, forKey: .pinnedServerCert)
        }

        private enum CodingKeys: String, CodingKey {
            case database
            case collections
            case endpoint
            case replicatorType
            case continuous
            case authenticator
            case pinnedServerCert
            case enableDocumentListener
            case enableAutoPurge
        }
        
        private enum AuthenticatorCodingKeys: String, CodingKey {
            case type
        }
    }
}
