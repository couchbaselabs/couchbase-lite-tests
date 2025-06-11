//
//  DocumentReplication.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor
import CouchbaseLiteSwift

//DocumentReplication:
//      type: object
//      required: ['collection', 'documentID', 'isPush']
//      properties:
//        collection:
//          type: string
//          example: 'store.cloths'
//        documentID:
//          type: string
//          example: 'doc1'
//        isPush:
//          type: boolean
//          example: true
//        flags:
//          type: array
//          items:
//            type: string
//            enum: [deleted, accessRemoved]
//            example: ['deleted']
//        error:
//          $ref: '#/components/schemas/Error'

extension ContentTypes {
    struct DocumentReplication : Content, CustomStringConvertible {
        let collection: String
        let documentID: String
        let isPush: Bool
        let flags: [DocumentReplicationFlags]
        let error: TestServerError?
        
        var description: String {
            var result = ""
            
            result += "DocumentReplication:\n"
            result += "\tcollection: \(collection)\n"
            result += "\tdocumentID: \(documentID)\n"
            result += "\tisPush: \(isPush.description)\n"
            result += "\tflags: \(flags)\n"
            result += "\terror: \(error.debugDescription)"
            
            return result
        }
    }
    enum DocumentReplicationFlags : String, Codable {
        case deleted = "deleted"
        case accessRemoved = "accessRemoved"
    }
}

extension ContentTypes.DocumentReplication {
    init(doc: CouchbaseLiteSwift.ReplicatedDocument, isPush: Bool) {
        var flags: [ContentTypes.DocumentReplicationFlags] = []
        if doc.flags.contains(.accessRemoved) { flags.append(.accessRemoved) }
        if doc.flags.contains(.deleted) { flags.append(.deleted) }
        
        self.collection = "\(doc.scope).\(doc.collection)"
        self.documentID = doc.id
        self.isPush = isPush
        self.flags = flags
        self.error = doc.error.map(TestServerError.cblError)
    }
}
