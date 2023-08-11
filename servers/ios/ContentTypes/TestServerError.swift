//
//  Error.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 02/08/2023.
//

import CouchbaseLiteSwift

//Error:
//      type: object
//      required: ['domain', 'code']
//      properties:
//        domain:
//          type: string
//          enum: [TESTSERVER, CBL, POSIX, SQLITE, FLEECE]
//          example: 'TESTSERVER'
//        code:
//          type: integer
//          format: int32
//          example: 1
//        message:
//          type: string
//          example: 'This is an error'

enum TestServerErrorDomain : String, Codable {
    case TESTSERVER = "TESTSERVER"
    case CBL = "CBL"
    case POSIX = "POSIX"
    case SQLITE = "SQLITE"
    case FLEECE = "FLEECE"
}

struct TestServerError : Error, Codable {
    let domain: TestServerErrorDomain
    let code: Int
    let message: String
    
    static let badRequest = TestServerError(domain: .TESTSERVER, code: 400, message: "Bad request.")
    static let cblDBNotOpen = TestServerError(domain: .CBL, code: CBLError.notOpen, message: "Database is not open.")
    static let cblDocNotFound = TestServerError(domain: .CBL, code: CBLError.notFound, message: "Could not find document.")
    static let internalErr = TestServerError(domain: .TESTSERVER, code: 500, message: "Internal server error.")
}
