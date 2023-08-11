//
//  ResetConfiguration.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

//ResetConfiguration:
//      type: object
//      properties:
//        datasets:
//          type: object
//          additionalProperties:
//            type: array
//            items:
//              type: string
//          example: { 'catalog': ['db1', 'db2'] }

extension ContentTypes {
    struct ResetConfiguration : Content {
        let datasets: Dictionary<String, Array<String>>
    }
}
