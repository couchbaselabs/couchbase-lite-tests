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
    let success: Bool
    let expected: AnyCodable?
    let actual: AnyCodable?
    
    private static func isEqual(_ left: Any?, _ right: Any?) -> Bool {
        switch (left, right) {
        case (nil, nil): return true
        case let (left as Bool, right as Bool): return left == right
        case let (left as Int, right as Int): return left == right
        case let (left as Double, right as Double): return left == right
        case let (left as String, right as String): return left == right
        case let (left as Array<Any>, right as Array<Any>): return isEqual(left, right)
        case let (left as Dictionary<String, Any>, right as Dictionary<String, Any>): return isEqual(left, right)
        case let (left as Blob, right as Blob): return isEqual(left, right)
        default:
            return false
        }
    }
    
    private static func isEqual(_ left: Blob, _ right: Blob) -> Bool {
        guard left == right
        else { return false }
        
        return left.content == right.content
    }
    
    private static func isEqual(_ left: Dictionary<String, Any>, _ right: Dictionary<String, Any>) -> Bool {
        if(left.count != right.count) {
            return false
        }
        
        for (key, leftValue) in left {
            if !right.keys.contains(key) {
                return false
            }
            let result = isEqual(leftValue, right[key])
            if !result {
                return false
            }
        }
        
        return true
    }
        
    private static func isEqual(_ left: Array<Any>, _ right: Array<Any>) -> Bool {
        if(left.count != right.count) {
            return false
        }
        
        for i in 0...(left.count - 1) {
            let result = isEqual(left[i], right[i])
            if !result {
                return false
            }
        }
        
        return true
    }
    
    static func isEqual(_ left: DocComparable, _ right: DocComparable) throws -> DocComparison {
        let leftDict = left.toDictionary()
        let rightDict = right.toDictionary()
        
        if(leftDict.count != rightDict.count) {
            return DocComparison(success: false, expected: try AnyCodable(leftDict), actual: try AnyCodable(rightDict))
        }
        
        for (leftKey, leftVal) in leftDict {
            if !rightDict.keys.contains(leftKey) {
                return DocComparison(success: false, expected: try AnyCodable(leftDict), actual: try AnyCodable(rightDict))
            }
            
            let success = isEqual(leftVal, rightDict[leftKey])
            if !success {
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
                
                return DocComparison(success: false, expected: try AnyCodable(leftCopy), actual: try AnyCodable(rightCopy))
            }
        }
        
        return DocComparison(success: true, expected: nil, actual: nil)
    }
}
