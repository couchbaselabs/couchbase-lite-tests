//
//  ResetConfiguration.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

//ResetConfiguration:
//    test:
//      description: |-
//        The name of the test that will be run next
//      type: string
//    databases:
//      description: |-
//        Contains database names as keys, with values are dictionaries descrbing how the databases
//        will be created.
//      type: object
//      nullable: true
//      additionalProperties:
//        type: object
//        oneOf:
//          - properties:
//              collections:
//                description: |-
//                  A list of fully qualified collection names (<scope>.<collection>) to be created in the database.
//                  Collections may be null, but if an array is provided, it may not be empty.
//                  The Collections parameter cannot be used together with dataset.'
//                type: array
//                nullable: true
//                items:
//                  type: string
//                example: ["_default.employees", "_default.departments"]
//          - properties:
//              dataset:
//                description: 'Dataset name. Cannot be used together with collections.'
//                type: string
//                example: "travel"
//      example: {'db1': {}, 'db2': {'collections': ["_default.employees"]}, 'db3': {'dataset': "travel"}}

extension ContentTypes {
    struct ResetConfiguration : Content {
        let test: String?
        let databases: Dictionary<String, Dictionary<String, AnyCodable>>?
    }
}
