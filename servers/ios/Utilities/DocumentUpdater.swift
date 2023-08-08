//
//  DocumentUpdater.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import CouchbaseLiteSwift

struct DocumentUpdater {
    public static func processUpdate(item: ContentTypes.DatabaseUpdateItem) {
        guard let collection = DatabaseManager.shared?.collection(item.collection)
        else { return }
        item.updatedProperties.forEach { updateDict in
            updateDict.forEach { keyPath, value in
                var parser = KeyPathParser(input: keyPath)
                if let components = parser.parse(),
                    !components.isEmpty,
                    let parentProperty = getParentProperty(collection: collection, docID: item.documentID, keyPathComponents: components) {
                        update(parentProperty: parentProperty, propertyKey: components.last!, value: value)
                }
            }
        }
        item.removedProperties.forEach { keyPath in
            var parser = KeyPathParser(input: keyPath)
            if let components = parser.parse(),
               !components.isEmpty,
               let parentProperty = getParentProperty(collection: collection, docID: item.documentID, keyPathComponents: components) {
                remove(parentProperty: parentProperty, propertyKey: components.last!)
            }
        }
    }
    
    private static func getParentProperty(collection: Collection, docID: String, keyPathComponents: [KeyPathComponent]) -> MutableObjectProtocol? {
        guard let doc = try? collection.document(id: docID)
        else { return nil }
        
        let mutableDoc = doc.toMutable()
        
        var current : MutableObjectProtocol? = mutableDoc
        
        // Ignore last as we want to return the parent of the target property
        for (i, component) in keyPathComponents.dropLast(1).enumerated() {
            
            guard let currentSafe = current
                    // Should throw error here
            else { fatalError("Error applying doc update - couldn't parse keypath") }
            
            let isLast = i == keyPathComponents.count - 1
            
            switch component {
            case .index(let index):
                switch keyPathComponents[i + 1] {
                    case .index:
                        current = currentSafe.array(at: index)
                    case .property:
                        current = currentSafe.dictionary(at: index)
                }

            case .property(let name):
                switch keyPathComponents[i + 1] {
                    case .index:
                        current = currentSafe.array(forKey: name)
                    case .property:
                        current = currentSafe.dictionary(forKey: name)
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
