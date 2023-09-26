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
        
        static let success = CompareResult(equal: true, reason: nil, keypath: nil)
        static func fail(reason: Reason, keypath: String) -> CompareResult {
            return CompareResult(equal: false, reason: reason, keypath: keypath)
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
        case let (left as Bool, right as Bool): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath)
        case let (left as Int, right as Int): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath)
        case let (left as Double, right as Double): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath)
        case let (left as String, right as String): return left == right ? .success : .fail(reason: .MismatchedProperty, keypath: keypath)
        case let (left as Array<Any>, right as Array<Any>): return try isEqual(left, right, keypath: keypath)
        case let (left as Dictionary<String, Any>, right as Dictionary<String, Any>): return try isEqual(left, right, keypath: keypath)
        case let (left as Blob, right as Blob): return isEqual(left, right, keypath: keypath)
        default:
            throw TestServerError(domain: .TESTSERVER, code: 500, message: "Internal error parsing unknown type.")
        }
    }
    
    private static func isEqual(_ left: Blob, _ right: Blob, keypath: String) -> CompareResult {
        // Compare blob properties
        guard left == right
        else { return .fail(reason: .MismatchedProperty, keypath: keypath) }
        
        // Both blobs content nil is unexpected behaviour
        // It might indicate missing blob files
        guard left.content != nil || right.content != nil
        else { return .fail(reason: .MissingBlobFile, keypath: keypath) }
        
        return left.content == right.content ? .success : .fail(reason: .MismatchedProperty, keypath: keypath)
    }
    
    private static func isEqual(_ left: Dictionary<String, Any>, _ right: Dictionary<String, Any>, keypath: String) throws -> CompareResult {
        for (key, leftValue) in left {
            if !right.keys.contains(key) {
                return .fail(reason: .MismatchedProperty, keypath: keypath + "." + key)
            }
            let result = try isEqual(leftValue, right[key], keypath: keypath + "." + key)
            if !result.equal {
                return result
            }
        }
        
        return .success
    }
        
    private static func isEqual(_ left: Array<Any>, _ right: Array<Any>, keypath: String) throws -> CompareResult {
        for i in 0...(left.count - 1) {
            let result = try isEqual(left[i], right[i], keypath: keypath + "[\(i)]")
            if !result.equal {
                return result
            }
        }
        
        return .success
    }
    
    static func isEqual(_ left: DocComparable, _ right: DocComparable, docID: String, qualifiedCollection: String) throws -> ContentTypes.VerifyResponse {
        let leftDict = left.toDictionary()
        let rightDict = right.toDictionary()
        
        for (leftKey, leftVal) in leftDict {
            if !rightDict.keys.contains(leftKey) {
                return ContentTypes.VerifyResponse(result: false, description: FailDescriptions.case4(docID: docID, qualifiedCollection: qualifiedCollection, keypath: leftKey), document: try AnyCodable(leftDict), expected: try AnyCodable(leftDict), actual: try AnyCodable(rightDict))
            }
            
            let result = try isEqual(leftVal, rightDict[leftKey], keypath: leftKey)
            if !result.equal {
                var leftCopy = leftDict
                var rightCopy = rightDict
                for key in leftCopy.keys {
                    if(key != leftKey) {
                        leftCopy.removeValue(forKey: key)
                    }
                }
                
                for key in rightCopy.keys {
                    if(key != leftKey) {
                        rightCopy.removeValue(forKey: key)
                    }
                }
                
                let description = result.reason == .MissingBlobFile ? FailDescriptions.case6(docID: docID, qualifiedCollection: qualifiedCollection, keypath: result.keypath ?? "") : FailDescriptions.case4(docID: docID, qualifiedCollection: qualifiedCollection, keypath: result.keypath ?? "")
                
                return ContentTypes.VerifyResponse(result: false, description: description, document: try AnyCodable(leftDict), expected: try AnyCodable(leftCopy), actual: try AnyCodable(rightCopy))
            }
        }
        
        return ContentTypes.VerifyResponse(result: true, description: "Successfully verified changes.")
    }
}
