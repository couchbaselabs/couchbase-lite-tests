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

extension ContentTypes.CollectionDocuments {
    public init?(collectionNames: [String]) {
        self.init()
        collectionNames.forEach { collectionName in
            guard let query = DatabaseManager.shared?.createQuery(queryString: "SELECT meta().id, meta().revisionID FROM \(collectionName)")
            else { return }
            guard let collectionDocs = try? query.execute().map({ result in ContentTypes.CollectionDoc(id: result.string(at: 0)!, rev: result.string(at: 1)!) })
            else { return }
            self[collectionName] = collectionDocs
        }
    }
}
