//
//  GetDocument.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 10/3/24.
//

import Vapor

extension ContentTypes {
    struct GetDocumentRequest : Content {
        let database: String
        let document: DocumentID
    }
}
