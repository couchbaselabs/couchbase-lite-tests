//
//  VerifyResponse.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import Vapor

extension ContentTypes {
    struct VerifyResponse : Content {
        let result: Bool
        let description: String?
        let document: AnyCodable?
        let expected: AnyCodable?
        let actual: AnyCodable?
        
        init(result: Bool, description: String? = nil, document: AnyCodable? = nil, expected: AnyCodable? = nil, actual: AnyCodable? = nil) {
            self.result = result
            self.description = description
            self.document = document
            self.expected = expected
            self.actual = actual
        }
    }
}
