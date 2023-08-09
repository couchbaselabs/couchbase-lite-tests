//
//  DocumentUpdater.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import CouchbaseLiteSwift

struct DocumentUpdater {
    public static func processUpdate(item: ContentTypes.DatabaseUpdateItem) throws {
        guard let collection = DatabaseManager.shared?.collection(item.collection)
        else { return }
        
        for updateDict in item.updatedProperties {
            for (keyPath, value) in updateDict {
                var parser = KeyPathParser(input: keyPath)
                guard let components = parser.parse(), !components.isEmpty
                else {
                    throw TestServerError(domain: .TESTSERVER, code: 400, message: "Invalid keypath.")
                }
                // Ensure first component is not an array index
                switch components.first! {
                case .index: do {
                    throw TestServerError(domain: .TESTSERVER, code: 400, message: "Invalid keypath.")
                }
                default: break
                }
                
                let parentProperty = try getParentProperty(collection: collection, docID: item.documentID, keyPathComponents: components)
                update(parentProperty: parentProperty, propertyKey: components.last!, value: value)
            }
        }
        
        for keyPath in item.removedProperties {
            var parser = KeyPathParser(input: keyPath)
            guard let components = parser.parse(), !components.isEmpty
            else {
                throw TestServerError(domain: .TESTSERVER, code: 400, message: "Invalid keypath.")
            }
            
            switch components.first! {
            case .index: do {
                throw TestServerError(domain: .TESTSERVER, code: 400, message: "Invalid keypath.")
            }
            default: break
            }
            
            let parentProperty = try getParentProperty(collection: collection, docID: item.documentID, keyPathComponents: components)
            
            remove(parentProperty: parentProperty, propertyKey: components.last!)
        }
    }
    
    private static func getParentProperty(collection: Collection, docID: String, keyPathComponents: [KeyPathComponent]) throws -> MutableObjectProtocol {
        guard let doc = try? collection.document(id: docID)
        else { throw TestServerError.cblDocNotFound }
        
        let mutableDoc = doc.toMutable()
        
        var current : MutableObjectProtocol = mutableDoc
        
        // Ignore last as we want to return the parent of the target property
        for (i, component) in keyPathComponents.dropLast(1).enumerated() {
            
            let nextIsArray: Bool = {
                if i < keyPathComponents.count - 1 {
                    switch keyPathComponents[i + 1] {
                    case .index:
                        return true
                    case .property:
                        return false
                    }
                }
                return false
            }()
            
            switch component {
            case .index(let index):
                // Backfill array with null if it does not reach index
                if index >= current.count {
                    if(index > current.count) {
                        for i in (current.count)...(index - 1) {
                            current.setValue(nil, at: i)
                        }
                    }
                    if(nextIsArray) {
                        current.setValue(MutableArrayObject(), at: index)
                    } else {
                        current.setValue(MutableDictionaryObject(), at: index)
                    }
                }
                
                if(nextIsArray) {
                    guard let arr = current.array(at: index)
                    else { throw TestServerError.internalErr }
                    current = arr
                } else {
                    guard let dict = current.dictionary(at: index)
                    else { throw TestServerError.internalErr }
                    current = dict
                }

            case .property(let name):
                // Create property if it does not exist
                if !current.contains(key: name) {
                    if(nextIsArray) {
                        current.setValue(MutableArrayObject(), forKey: name)
                    } else {
                        current.setValue(MutableDictionaryObject(), forKey: name)
                    }
                }
                
                if(nextIsArray) {
                    guard let arr = current.array(forKey: name)
                    else { throw TestServerError.internalErr }
                    current = arr
                } else {
                    guard let dict = current.dictionary(forKey: name)
                    else { throw TestServerError.internalErr }
                    current = dict
                }
            }
        }
        
        return current
    }
    
    private static func update(parentProperty: MutableObjectProtocol, propertyKey: KeyPathComponent, value: Any) {
        switch propertyKey {
        case .index(let index):
            _ = parentProperty.setValue(value, at: index)
        case .property(let name):
            _ = parentProperty.setValue(value, forKey: name)
        }
    }
    
    private static func remove(parentProperty: MutableObjectProtocol, propertyKey: KeyPathComponent) {
        switch propertyKey {
        case .index(let index):
            _ = parentProperty.removeValue(at: index)
        case .property(let name):
            _ = parentProperty.removeValue(forKey: name)
        }
    }
}
