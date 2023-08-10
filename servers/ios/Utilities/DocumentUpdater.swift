//
//  DocumentUpdater.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import CouchbaseLiteSwift

struct DocumentUpdater {
    public static func processUpdate(item: ContentTypes.DatabaseUpdateItem, inDB dbName: String) throws {
        guard let collection = try DatabaseManager.shared?.collection(item.collection, inDB: dbName)
        else { throw TestServerError.cblDBNotOpen }
        
        if let updatedProperties = item.updatedProperties {
            for updateDict in updatedProperties {
                for (keyPath, value) in updateDict {
                    var parser = KeyPathParser(input: keyPath)
                    guard let components = try parser.parse(), !components.isEmpty
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
        }
        
        if let removedProperties = item.removedProperties {
            for keyPath in removedProperties {
                var parser = KeyPathParser(input: keyPath)
                guard let components = try parser.parse(), !components.isEmpty
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
                        backfillArray(array: current, uptoInclusive: index)
                    }
                    if(nextIsArray) {
                        current.setValue(MutableArrayObject(), at: index)
                        
                    } else {
                        current.setValue(MutableDictionaryObject(), at: index)
                    }
                }
                
                if(nextIsArray) {
                    guard let arr = current.array(at: index)
                    // If arr doesn't exist, this component was probably a scalar
                    else { throw TestServerError.badRequest }
                    current = arr
                } else {
                    guard let dict = current.dictionary(at: index)
                    // If dict doesn't exist, this component was probably a scalar
                    else { throw TestServerError.badRequest }
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
                    // If arr doesn't exist, this component was probably a scalar
                    else { throw TestServerError.badRequest }
                    current = arr
                } else {
                    guard let dict = current.dictionary(forKey: name)
                    // If dict doesn't exist, this component was probably a scalar
                    else { throw TestServerError.badRequest }
                    current = dict
                }
            }
        }
        
        return current
    }
    
    private static func update(parentProperty: MutableObjectProtocol, propertyKey: KeyPathComponent, value: AnyCodable) {
        switch propertyKey {
        case .index(let index):
            backfillArray(array: parentProperty, uptoInclusive: index)
            parentProperty.setValue(value.value, at: index)
        case .property(let name):
            parentProperty.setValue(value.value, forKey: name)
        }
    }
    
    private static func backfillArray(array: MutableObjectProtocol, uptoInclusive: Int) {
        if uptoInclusive > array.count,
           let array = array as? MutableArrayObject {
            for _ in array.count...uptoInclusive {
                array.addValue(nil)
            }
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
