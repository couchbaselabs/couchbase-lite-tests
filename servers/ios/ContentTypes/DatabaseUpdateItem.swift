//
//  DatabaseUpdateItem.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import Vapor

//DatabaseUpdateItem:
//      type: object
//      required: ['type', 'collection', 'documentID']
//      properties:
//        type:
//          type: string
//          enum: ['UPDATE', 'DELETE', 'PURGE']
//          example: 'UPDATE'
//        collection:
//          type: string
//          example: 'store.cloths'
//        documentID:
//          type: string
//          example: 'doc1'
//        updatedProperties:
//          type: array
//          items:
//            type: object
//            additionalProperties: { }
//            example: [
//              {'people[47].address': {'street': 'Oak St. ', 'city': 'Auburn'} },
//              {'people[3].address': {'street': 'Elm St. ', 'city': 'Sibley'} }
//            ]
//        removedProperties:
//          type: array
//          items:
//            type: string
//            example: [ 'people[22].address', 'people[3]' ]

//updatedProperties:
//
//        An array of objects. Each object contains one or more keys that are key paths into the document to be updated with the
//        values associated with the keys. The objects in the array are evaluated in their natural order.
//
//        The keypath identifies a unique location in the document's property tree starting from the root that follows
//        dictionary properties and array elements. The keypath looks like "foo.bar[1].baz" - The keypath components are
//        separated by dot ('.'). Each path is represented by the key name in a dictionary object, and the index brackets
//        at the end of the key name points to an array element in an array object. A '\' can be used to escape a special
//        character ('.', '[', ']', '\' or '$') in the key name.
//
//        The value at the location specified by the keypath is replaced with the value associated with the keypath, in the object
//        regardless of its type. When a path in the keypath refers to a non-existent property, the key is added and
//        its value set as a dictionary or an array depending on the type of the path.
//
//        When a path in the keypath includes an array index that is out of bounds (the array is smaller than the specified index), the array
//        is padded with nulls until it is exactly large enough to make the specified index legal.
//
//        When a path (dictionary or array) in the keypath doesn't match the actual value type, the error will be returned.

extension ContentTypes {
    enum ActionType : String, Codable {
        case UPDATE = "UPDATE"
        case DELETE = "DELETE"
        case PURGE = "PURGE"
    }
    
    struct DatabaseUpdateItem : Content {
        let type: ActionType
        let collection: String
        let documentID: String
        let updatedProperties: Array<Dictionary<String, AnyCodable>>?
        let removedProperties: Array<String>?
        let updatedBlobs: Dictionary<String, String>?
    }
}
