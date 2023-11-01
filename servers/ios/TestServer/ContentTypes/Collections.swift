//
//  Collections.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

//Collections:
//      type: object
//      required: ['database', 'collections']
//      properties:
//        database:
//          type: string
//          example: 'db1'
//        collections:
//          type: array
//          items:
//            type: string
//          example: ['catalog.cloths', 'catalog.shoes']

extension ContentTypes {
    struct Collections : Content {        
        let database : String
        let collections: Array<String>
    }
}
