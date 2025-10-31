//
//  DocumentUpdater.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import CouchbaseLiteSwift

struct DocumentUpdater {
    public static func processUpdate(dbManager:DatabaseManager, item: ContentTypes.DatabaseUpdateItem, inDB dbName: String) throws {
        Log.log(level: .debug, message: "Processing /updateDatabase request for database '\(dbName)'")
        
        guard let collection = try dbManager.collection(item.collection, inDB: dbName)
        else {
            Log.log(level: .error, message: "Failed to perform update, database '\(dbName)' not open.")
            throw TestServerError.cblDBNotOpen
        }
        
        let doc = try? collection.document(id: item.documentID)
        
        let mutableDoc = doc?.toMutable() ?? MutableDocument(id: item.documentID)
        
        try update(
            dbManager: dbManager,
            doc: mutableDoc,
            updatedProperties: item.updatedProperties,
            removedProperties: item.removedProperties,
            updatedBlobs: item.updatedBlobs)
        
        do {
            try collection.save(document: mutableDoc)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    // This function does not save the updated doc, the caller must do that if desired
    public static func update(dbManager:DatabaseManager, doc: MutableDocument, updatedProperties: Array<Dictionary<String, AnyCodable>>?, removedProperties: Array<String>?, updatedBlobs: Dictionary<String, String>?) throws {
        Log.log(level: .debug, message: "Processing update for document '\(doc.id)'")
        
        if let removedProperties = removedProperties {
            Log.log(level: .debug, message: "Removing properties of document '\(doc.id)'")
            for keyPath in removedProperties {
                var parser = KeyPathParser(input: keyPath)
                
                let components = try parser.parse()
                
                let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                
                Log.log(level: .debug, message: "Removing property of document '\(doc.id)' at keypath '\(keyPath)'")
                remove(parentProperty: parentProperty, propertyKey: components.last!)
            }
        }
        
        if let updatedProperties = updatedProperties {
            Log.log(level: .debug, message: "Updating properties of document '\(doc.id)'")
            for updateDict in updatedProperties {
                for (keyPath, value) in updateDict {
                    var parser = KeyPathParser(input: keyPath)
                    
                    let components = try parser.parse()
                    
                    let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                    
                    Log.log(level: .debug, message: "Updating property of document '\(doc.id)' at keypath '\(keyPath)'")
                    updateProperty(parentProperty: parentProperty, propertyKey: components.last!, value: value)
                }
            }
        }
        
        if let updatedBlobs = updatedBlobs {
            Log.log(level: .debug, message: "Updating blobs of document '\(doc.id)'")
            for (keyPath, filename) in updatedBlobs {
                var parser = KeyPathParser(input: keyPath)
                let components = try parser.parse()
                let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                let blob = try dbManager.loadBlob(filename: filename)
                
                Log.log(level: .debug, message: "Updating property of document '\(doc.id)' at keypath '\(keyPath)' with blob '\(filename)'")
                updateProperty(parentProperty: parentProperty, propertyKey: components.last!, blob: blob)
            }
        }
        
    }
    
    // Navigate the KeyPath of the document to find the parent property of the property to be updated / removed
    private static func getParentProperty(mutableDoc: MutableDocument, keyPathComponents: [KeyPathComponent]) throws -> MutableObjectProtocol {
        Log.log(level: .debug, message: "Navigating KeyPath of document '\(mutableDoc.id)'")
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
                        Log.log(level: .error, message: "Failed to navigate KeyPath, KeyPath attempted to index a scalar value")
                        throw TestServerError.badRequest("Scalar cannot be indexed: \(current)")
                    }
                    current = arr
                } else {
                    guard let dict = current.dictionary(at: index)
                    // If dict doesn't exist, this component was probably a scalar
                    else {
                        Log.log(level: .error, message: "Failed to navigate KeyPath, KeyPath attempted to index a scalar value")
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
                        Log.log(level: .error, message: "Failed to navigate KeyPath, KeyPath attempted to access a property of a scalar value")
                        throw TestServerError.badRequest("Scalar cannot have child properties, value: \(current)")
                    }
                    current = arr
                } else {
                    guard let dict = current.dictionary(forKey: name)
                    // If dict doesn't exist, this component was probably a scalar
                    else {
                        Log.log(level: .error, message: "Failed to navigate KeyPath, KeyPath attempted to access a property of a scalar value")
                        throw TestServerError.badRequest("Scalar cannot have child properties, value: \(current)")
                    }
                    current = dict
                }
            }
        }
        
        Log.log(level: .debug, message: "Navigated KeyPath of document '\(mutableDoc.id)' to reach parent property")
        return current
    }
    
    private static func updateProperty(parentProperty: MutableObjectProtocol, propertyKey: KeyPathComponent, value: AnyCodable) {
        switch propertyKey {
        case .index(let index):
            backfillArray(array: parentProperty, uptoInclusive: index)
            parentProperty.setValue(value.value, at: index)
        case .property(let name):
            parentProperty.setValue(value.value, forKey: name)
        }
    }
    
    private static func updateProperty(parentProperty: MutableObjectProtocol, propertyKey: KeyPathComponent, blob: Blob) {
        switch propertyKey {
        case .index(let index):
            backfillArray(array: parentProperty, uptoInclusive: index)
            parentProperty.setValue(blob, at: index)
        case .property(let name):
            parentProperty.setValue(blob, forKey: name)
        }
    }
    
    private static func backfillArray(array: MutableObjectProtocol, uptoInclusive: Int) {
        Log.log(level: .debug, message: "Backfilling array to index \(uptoInclusive)")
        if uptoInclusive <= array.count {
            return
        }
        
        if let array = array as? MutableArrayObject {
            for _ in array.count...uptoInclusive {
                array.addValue(nil)
            }
        } else {
            Log.log(level: .debug, message: "Warning: Attempt to call `backfillArray()` on a non-array (dict or scalar)")
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
