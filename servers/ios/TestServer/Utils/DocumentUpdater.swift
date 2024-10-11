//
//  DocumentUpdater.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import CouchbaseLiteSwift

struct DocumentUpdater {
    public static func processUpdate(dbManager:DatabaseManager, item: ContentTypes.DatabaseUpdateItem, inDB dbName: String) throws {
        TestServer.logger.log(level: .debug, "Processing /updateDatabase request for database '\(dbName)'")
        
        guard let collection = try dbManager.collection(item.collection, inDB: dbName)
        else {
            TestServer.logger.log(level: .error, "Failed to perform update, database '\(dbName)' not open.")
            throw TestServerError.cblDBNotOpen
        }
        
        let doc = try? collection.document(id: item.documentID)
        
        let mutableDoc = doc?.toMutable() ?? MutableDocument(id: item.documentID)
        
        try update(doc: mutableDoc, updatedProperties: item.updatedProperties, removedProperties: item.removedProperties, updatedBlobs: item.updatedBlobs)
        do {
            try collection.save(document: mutableDoc)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
    }
    
    // This function does not save the updated doc, the caller must do that if desired
    public static func update(doc: MutableDocument, updatedProperties: Array<Dictionary<String, AnyCodable>>?, removedProperties: Array<String>?, updatedBlobs: Dictionary<String, String>?) throws {
        TestServer.logger.log(level: .debug, "Processing update for document '\(doc.id)'")
        
        if let removedProperties = removedProperties {
            TestServer.logger.log(level: .debug, "Removing properties of document '\(doc.id)'")
            for keyPath in removedProperties {
                var parser = KeyPathParser(input: keyPath)
                
                let components = try parser.parse()
                
                let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                
                TestServer.logger.log(level: .debug, "Removing property of document '\(doc.id)' at keypath '\(keyPath)'")
                remove(parentProperty: parentProperty, propertyKey: components.last!)
            }
        }
        
        if let updatedProperties = updatedProperties {
            TestServer.logger.log(level: .debug, "Updating properties of document '\(doc.id)'")
            for updateDict in updatedProperties {
                for (keyPath, value) in updateDict {
                    var parser = KeyPathParser(input: keyPath)
                    
                    let components = try parser.parse()
                    
                    let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                    
                    TestServer.logger.log(level: .debug, "Updating property of document '\(doc.id)' at keypath '\(keyPath)'")
                    updateProperty(parentProperty: parentProperty, propertyKey: components.last!, value: value)
                }
            }
        }
        
        if let updatedBlobs = updatedBlobs {
            TestServer.logger.log(level: .debug, "Updating blobs of document '\(doc.id)'")
            for (keyPath, filename) in updatedBlobs {
                var parser = KeyPathParser(input: keyPath)
                let components = try parser.parse()
                let parentProperty = try getParentProperty(mutableDoc: doc, keyPathComponents: components)
                let blob = try createBlob(filename: filename)
                
                TestServer.logger.log(level: .debug, "Updating property of document '\(doc.id)' at keypath '\(keyPath)' with blob '\(filename)'")
                updateProperty(parentProperty: parentProperty, propertyKey: components.last!, blob: blob)
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
    
    private static func createBlob(filename: String) throws -> Blob {
        let filenameComponents = filename.components(separatedBy: ".")
        
        guard filenameComponents.count == 2
        else {
            TestServer.logger.log(level: .error, "Invalid filename given for blob")
            throw TestServerError.badRequest("Invalid blob filename '\(filename)'.")
        }
        
        let fileExtension = filenameComponents.last!
        let res = ("blobs" as NSString).appendingPathComponent(filenameComponents.first!)
        guard let blobURL = Bundle.main.url(forResource: res, withExtension: fileExtension)
        else {
            TestServer.logger.log(level: .error, "No blob found at given filename")
            throw TestServerError.badRequest("Blob '\(filename)' not found.")
        }
        
        let contentType: String = {
            switch fileExtension {
            case "jpeg", "jpg": return "image/jpeg"
            default: return "application/octet-stream"
            }
        }()
        
        do {
            return try Blob(contentType: contentType, fileURL: blobURL)
        } catch(let error as NSError) {
            throw TestServerError(domain: .CBL, code: error.code, message: error.localizedDescription)
        }
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
