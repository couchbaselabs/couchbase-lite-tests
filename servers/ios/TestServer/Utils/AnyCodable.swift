//
//  AnyCodable.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 09/08/2023.
//

import Foundation
import CouchbaseLiteSwift

struct AnyCodable: Codable {
    let value: Any

    init(_ value: Any) throws {
        // Potentially unwrap if value is AnyCodable
        let value = value is AnyCodable ? (value as! AnyCodable).value : value
        switch value {
        case let value as NSNull:
            self.value = value
        case let value as Bool:
            self.value = value
        case let value as Int:
            self.value = value
        case let value as Double:
            self.value = value
        case let value as String:
            self.value = value
        case let value as [Any]:
            self.value = try value.map { try AnyCodable($0) }
        case let value as [String : Any]:
            self.value = try value.mapValues { try AnyCodable($0) }
            // Blob gets encoded as blob properties
        case let value as CouchbaseLiteSwift.Blob:
            self.value = try value.properties.mapValues { try AnyCodable($0) }
        default:
            throw TestServerError(domain: .TESTSERVER, code: 500, message: "Internal error parsing value type: \(value)")
        }
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self.value = NSNull()
        } else if let value = try? container.decode(Bool.self) {
            self.value = value
        } else if let value = try? container.decode(Int.self) {
            self.value = value
        } else if let value = try? container.decode(Double.self) {
            self.value = value
        } else if let value = try? container.decode(String.self) {
            self.value = value
        } else if let value = try? container.decode([AnyCodable].self) {
            self.value = value.map { $0.value }
        } else if let value = try? container.decode([String: AnyCodable].self) {
            self.value = value.mapValues { $0.value }
        } else {
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "AnyCodable value cannot be decoded")
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self.value {
        case _ as NSNull:
            try container.encodeNil()
        case let value as Bool:
            try container.encode(value)
        case let value as Int:
            try container.encode(value)
        case let value as Double:
            try container.encode(value)
        case let value as String:
            try container.encode(value)
        case let value as [Any]:
            try container.encode(value.map { try AnyCodable($0) })
        case let value as [String: Any]:
            try container.encode(value.mapValues { try AnyCodable($0) })
        default:
            throw EncodingError.invalidValue(self.value, EncodingError.Context(codingPath: container.codingPath, debugDescription: "AnyCodable value cannot be encoded"))
        }
    }
}
