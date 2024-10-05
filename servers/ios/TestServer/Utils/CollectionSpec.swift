//
//  CollectionSpec.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/3/24.
//

import Foundation

struct CollectionSpec {
    let scope: String
    
    let collection: String
    
    init(_ name: String) throws {
        let components = name.components(separatedBy: ".")
        if components.count != 2 {
            throw TestServerError.badRequest("Invalid collection name format")
        }
        scope = components[0]
        collection = components[1]
    }
}
