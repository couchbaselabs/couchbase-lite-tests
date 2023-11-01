//
//  VerifyRequest.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import Vapor

extension ContentTypes {
    struct VerifyRequest : Content {
        let database: String
        let snapshot: String
        let changes: Array<DatabaseUpdateItem>
    }
}
