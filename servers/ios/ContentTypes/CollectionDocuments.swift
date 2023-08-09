//
//  CollectionDocuments.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import Vapor
import CouchbaseLiteSwift

extension ContentTypes {
    struct CollectionDoc : Content {
        let id: String
        let rev: String
    }
    
    // Key is scope.collection
    typealias CollectionDocuments = Dictionary<String, Array<CollectionDoc>>
}
