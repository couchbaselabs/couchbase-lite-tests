//
//  UpdateRequest.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 09/08/2023.
//

import Vapor

extension ContentTypes {
    struct UpdateRequest : Content {
        let database: String
        let updates: Array<DatabaseUpdateItem>
    }
}
