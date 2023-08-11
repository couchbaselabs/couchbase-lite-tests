//
//  StartReplicatorRequest.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 11/08/2023.
//

import Vapor

extension ContentTypes {
    struct StartReplicatorRequest : Content {
        let config: ReplicatorConfiguration
        let reset: Bool?
    }
}
