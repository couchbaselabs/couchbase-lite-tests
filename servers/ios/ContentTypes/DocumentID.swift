//
//  DocumentID.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

//DocumentID:
//      type: object
//      required: ['collection', 'id']
//      properties:
//        collection:
//          type: string
//          example: 'store.cloths'
//        id:
//          type: string
//          example: 'doc1'

extension ContentTypes {
    struct DocumentID : Content {
        let collection: String
        let id: String
    }
}
