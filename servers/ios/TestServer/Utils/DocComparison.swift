//
//  DocComparison.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 10/08/2023.
//

import Vapor
import CouchbaseLiteSwift

protocol DocComparable {
    func toDictionary() -> Dictionary<String, Any>
}

extension Document : DocComparable {}
extension DictionaryObject : DocComparable {}

extension Dictionary<String, Any> {
    func toCodable() throws -> Dictionary<String, AnyCodable> {
        var result: [String: AnyCodable] = [:]
        
        for (key, val) in self {
            result[key] = try AnyCodable(val)
        }
        
        return result
    }
}

struct DocComparison : Content {
    struct CompareResult {
        let equal: Bool
        let reason: Reason?
        let keypath: String?
        let expected: Any?
        let actual: Any?
        
        
        static let success = CompareResult(equal: true, reason: nil, keypath: nil, expected: nil, actual: nil)
        static func fail(reason: Reason, keypath: String, expected: Any?, actual: Any?) -> CompareResult {
            return CompareResult(equal: false, reason: reason, keypath: keypath, expected: expected, actual: actual)
        }
        
        enum Reason {
            case MismatchedProperty
            case MissingBlobFile
        }
    }
    
    struct FailDescriptions {
        // Document should exist in the collection but it doesn't exist to verify
        static func case1(docID: String, qualifiedCollection: String) -> String {
            "Document '\(docID)' in '\(qualifiedCollection)' was not found"
        }
        // Document should be deleted but it wasn't
        static func case2(docID: String, qualifiedCollection: String) -> String {
            "Document '\(docID)' in '\(qualifiedCollection)' was not deleted"
        }
        // Document should be purged but it wasn't
        static func case3(docID: String, qualifiedCollection: String) -> String {
            "Document '\(docID)' in '\(qualifiedCollection)' was not purged"
        }
        // Document has unexpected properties
        static func case4(docID: String, qualifiedCollection: String, keypath: String) -> String {
            "Document '\(docID)' in '\(qualifiedCollection)' had unexpected properties at key '\(keypath)'"
        }
        // Document shouldn't exist (null value in snapshot), but the document does exist
        static func case5(docID: String, qualifiedCollection: String) -> String {
            "Document '\(docID)' in '\(qualifiedCollection)' should not exist"
        }
        // Blob file doesn't exist in the database
        static func case6(docID: String, qualifiedCollection: String, keypath: String) -> String {
            "Document '\(docID)' in '\(qualifiedCollection)' had non-existing blob at key '\(keypath)'"
        }
    }
    
    private static func isEqual(_ left: Any?, _ right: Any?, keypath: String) throws -> CompareResult {
        switch (left, right) {
        case (nil, nil): return .success
        case let (left as NSNull, right as NSNull): return .success
        case let (left as Bool, right as Bool): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
        case let (left as Int, right as Int): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
        case let (left as Double, right as Double): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
        case let (left as String, right as String): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
        case let (left as Array<Any>, right as Array<Any>): return try isEqual(left, right, keypath: keypath)
        case let (left as Dictionary<String, Any>, right as Dictionary<String, Any>): return try isEqual(left, right, keypath: keypath)
        case let (left as Blob, right as Blob): return isEqual(left, right, keypath: keypath)
        default:
            return .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
        }
    }
    
    private static func isEqual(_ left: Blob, _ right: Blob, keypath: String) -> CompareResult {
        // Compare blob properties
        guard left == right else {
            return .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
        }
        
        // Both blobs content nil is unexpected behaviour
        // It might indicate missing blob files
        guard left.content != nil || right.content != nil else {
            return .fail(reason: .MissingBlobFile, keypath: keypath, expected: nil, actual: nil)
        }
        
        return left.content == right.content ? .success : .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
    }
    
    private static func isEqual(_ left: Dictionary<String, Any>, _ right: Dictionary<String, Any>, keypath: String) throws -> CompareResult {
        var checkedKeys: Set<String> = []
        
        for key in left.keys {
            let path = keypath.isEmpty ? key : keypath + "." + key
            
            if !right.keys.contains(key) {
                return .fail(reason: .MismatchedProperty, keypath: path, expected: left[key]!, actual: nil)
            }
            
            let leftValue = left[key]!
            
            let result = try isEqual(leftValue, right[key], keypath: path)
            if !result.equal {
                return result
            }
            checkedKeys.insert(key)
        }
        
        for key in right.keys where !checkedKeys.contains(key) {
            let path = keypath.isEmpty ? key : keypath + "." + key
            return .fail(reason: .MismatchedProperty, keypath: path, expected: nil, actual: right[key]!)
        }
        
        return .success
    }
        
    private static func isEqual(_ left: Array<Any>, _ right: Array<Any>, keypath: String) throws -> CompareResult {
        if left.count != right.count {
            return .fail(reason: .MismatchedProperty, keypath: keypath, expected: left, actual: right)
        }
        if left.count > 0 {
            for i in 0...(left.count - 1) {
                let result = try isEqual(left[i], right[i], keypath: keypath + "[\(i)]")
                if !result.equal {
                    return result
                }
            }
        }
        return .success
    }
    
    static func isEqual(_ left: DocComparable, _ right: DocComparable, docID: String, qualifiedCollection: String) throws -> ContentTypes.VerifyResponse {
        let leftDict = left.toDictionary()
        let rightDict = right.toDictionary()
        
        let result = try isEqual(leftDict, rightDict, keypath: "")
        
        if !result.equal {
            let description = result.reason == .MissingBlobFile ?
                FailDescriptions.case6(docID: docID, qualifiedCollection: qualifiedCollection, keypath: result.keypath ?? "??") :
                FailDescriptions.case4(docID: docID, qualifiedCollection: qualifiedCollection, keypath: result.keypath ?? "??")
            
            if (result.keypath!.isEmpty) {
                print("")
            }
            
            let expected = result.expected != nil ? try AnyCodable(result.expected!) : nil
            let actual = result.actual != nil ? try AnyCodable(result.actual!) : nil
             
            return ContentTypes.VerifyResponse(result: false, description: description, document: try AnyCodable(rightDict), expected:  expected, actual: actual)
        }
        
        return ContentTypes.VerifyResponse(result: true, description: "Successfully verified changes.")
    }
}
