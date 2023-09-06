//
//  DocumentUpdater.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import CouchbaseLiteSwift

struct DocumentUpdater {
    public static func processUpdate(item: ContentTypes.DatabaseUpdateItem, inDB dbName: String) throws {
        TestServer.logger.log(level: .debug, "Processing /updateDatabase request for database '\(dbName)'")
        
        guard let collection = try DatabaseManager.shared?.collection(item.collection, inDB: dbName)
        else {
            TestServer.logger.log(level: .error, "Failed to perform update, database '\(dbName)' not open.")
            throw TestServerError.cblDBNotOpen
        }
        
        let doc = try? collection.document(id: item.documentID)
        
        let mutableDoc = doc?.toMutable() ?? MutableDocument(id: item.documentID)
        
        try update(doc: mutableDoc, updatedProperties: item.updatedProperties, removedProperties: item.removedProperties)
        do {
            try collection.save(document: mutableDoc)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    // This function does not save the updated doc, the caller must do that if desired
    public static func update(doc: MutableDocument, updatedProperties: Array<Dictionary<String, AnyCodable>>? = nil, removedProperties: Array<String>? = nil) throws {
        TestServer.logger.log(level: .debug, "Processing update for document '\(doc.id)'")
        
        if let updatedProperties = updatedProperties {
            TestServer.logger.log(level: .debug, "Updating properties of document '\(doc.id)'")
            for updateDict in updatedProperties {
                for (keyPath, value) in updateDict {
                    var parser = KeyPathParser(input: keyPath)
                    
                    let components = try parser.parse()
                    
                    let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                    update(parentProperty: parentProperty, propertyKey: components.last!, value: value)
                }
            }
        }
        
        if let removedProperties = removedProperties {
            for keyPath in removedProperties {
                var parser = KeyPathParser(input: keyPath)
                
                let components = try parser.parse()
                
                let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                
                remove(parentProperty: parentProperty, propertyKey: components.last!)
            }
        }
        
    }
    
    // Navigate the KeyPath of the document to find the parent property of the property to be updated / removed
    private static func getParentProperty(mutableDoc: MutableDocument, keyPathComponents: [KeyPathComponent]) throws -> MutableObjectProtocol {
        TestServer.logger.log(level: .debug, "Navigating KeyPath of document '\(mutableDoc.id)'")
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
                    else {
                        TestServer.logger.log(level: .error, "Failed to navigate KeyPath, KeyPath attempted to index a scalar value")
                        throw TestServerError.badRequest("Scalar cannot be indexed: \(current)")
                    }
                    current = arr
                } else {
                    guard let dict = current.dictionary(at: index)
                    // If dict doesn't exist, this component was probably a scalar
                    else {
                        TestServer.logger.log(level: .error, "Failed to navigate KeyPath, KeyPath attempted to index a scalar value")
                        throw TestServerError.badRequest("Scalar cannot be indexed: \(current)")
                    }
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
                    else {
                        TestServer.logger.log(level: .error, "Failed to navigate KeyPath, KeyPath attempted to access a property of a scalar value")
                        throw TestServerError.badRequest("Scalar cannot have child properties, value: \(current)")
                    }
                    current = arr
                } else {
                    guard let dict = current.dictionary(forKey: name)
                    // If dict doesn't exist, this component was probably a scalar
                    else {
                        TestServer.logger.log(level: .error, "Failed to navigate KeyPath, KeyPath attempted to access a property of a scalar value")
                        throw TestServerError.badRequest("Scalar cannot have child properties, value: \(current)")
                    }
                    current = dict
                }
            }
        }
        
        TestServer.logger.log(level: .debug, "Navigated KeyPath of document '\(mutableDoc.id)' to reach parent property")
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
        TestServer.logger.log(level: .debug, "Backfilling array to index \(uptoInclusive)")
        if uptoInclusive <= array.count {
            return
        }
        
        if let array = array as? MutableArrayObject {
            for _ in array.count...uptoInclusive {
                array.addValue(nil)
            }
        } else {
            TestServer.logger.log(level: .debug, "Warning: Attempt to call `backfillArray()` on a non-array (dict or scalar)")
        }
    }
    
    private static func remove(parentProperty: MutableObjectProtocol, propertyKey: KeyPathComponent) {
        switch propertyKey {
        case .index(let index):
            parentProperty.removeValue(at: index)
        case .property(let name):
            parentProperty.removeValue(forKey: name)
        }
    }
}
