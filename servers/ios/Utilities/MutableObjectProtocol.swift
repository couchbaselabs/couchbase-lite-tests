//
//  DocumentUpdater.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import CouchbaseLiteSwift

protocol MutableObjectProtocol {
    func setValue(_ value: Any?, at index: Int) -> Self
    func setValue(_ value: Any?, forKey key: String) -> Self
    func removeValue(at index: Int) -> Self
    func removeValue(forKey key: String) -> Self
    func array(at index: Int) -> MutableArrayObject?
    func dictionary(at index: Int) -> MutableDictionaryObject?
    func array(forKey key: String) -> MutableArrayObject?
    func dictionary(forKey key: String) -> MutableDictionaryObject?
}

extension MutableArrayObject : MutableObjectProtocol {
    func removeValue(forKey key: String) -> Self {
        print("Warning: attempted to call `removeValue(forKey:)` on MutableArrayObject")
        return self
    }
    
    func setValue(_ value: Any?, forKey key: String) -> Self {
        print("Warning: attempted to call `setValue(forKey:)` on MutableArrayObject")
        return self
    }
    
    func array(forKey key: String) -> CouchbaseLiteSwift.MutableArrayObject? {
        print("Warning: attempted to call `array(forKey:)` on MutableArrayObject")
        return nil
    }
    
    func dictionary(forKey key: String) -> CouchbaseLiteSwift.MutableDictionaryObject? {
        print("Warning: attempted to call `dictionary(forKey:)` on MutableArrayObject")
        return nil
    }
}

extension MutableDictionaryObject : MutableObjectProtocol {
    func removeValue(at index: Int) -> Self {
        print("Warning: attempted to call `removeValue(at index:)` on MutableDictionaryObject")
        return self
    }
    
    func setValue(_ value: Any?, at index: Int) -> Self {
        print("Warning: attempted to call `setValue(at index:)` on MutableDictionaryObject")
        return self
    }
    
    func array(at index: Int) -> CouchbaseLiteSwift.MutableArrayObject? {
        print("Warning: attempted to call `array(at index:)` on MutableDictionaryObject")
        return nil
    }
    
    func dictionary(at index: Int) -> CouchbaseLiteSwift.MutableDictionaryObject? {
        print("Warning: attempted to call `dictionary(at index:)` on MutableDictionaryObject")
        return nil
    }
}

extension MutableDocument : MutableObjectProtocol {
    func removeValue(at index: Int) -> Self {
        print("Warning: attempted to call `removeValue(at index:)` on MutableDocument")
        return self
    }
    
    func setValue(_ value: Any?, at index: Int) -> Self {
        print("Warning: attempted to call `setValue(at index:)` on MutableDocument")
        return self
    }
    
    func array(at index: Int) -> CouchbaseLiteSwift.MutableArrayObject? {
        print("Warning: attempted to call `array(at index:)` on MutableDocument")
        return nil
    }
    
    func dictionary(at index: Int) -> CouchbaseLiteSwift.MutableDictionaryObject? {
        print("Warning: attempted to call `dictionary(at index:)` on MutableDocument")
        return nil
    }
}
