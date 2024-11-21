//
//  KeyPathParser.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 08/08/2023.
//

import Foundation
import CouchbaseLiteSwift

enum KeyPathComponent {
    case property(String)
    case index(Int)
}

struct KeyPathParser {
    private var input: String
    private var index: String.Index
    
    init(input: String) {
        self.input = input
        Log.log(level: .debug, message: "Parsing KeyPath '\(input)'")
        self.index = input.startIndex
    }
    
    public mutating func parse() throws -> [KeyPathComponent] {
        var components: [KeyPathComponent] = []
        
        // Skip optional "$."
        if input.hasPrefix("$.") {
            advance(by: 2)
        }
        
        // Parse first component
        // First component should always be a property
        // If there is no first component, this fails
        if let component = try parseProperty(first: true) {
            components.append(component)
        } else {
            Log.log(level: .error, message: "Error parsing KeyPath, First KeyPath component should be a property.")
            throw TestServerError.badRequest("First KeyPath component should be a property.")
        }
        
        // Parse any remaining components
        while let component = (peek() == "." ? try parseProperty() : peek() == "[" ? try parseIndex() : nil) {
            components.append(component)
        }
        
        // We can't parse any more valid components, but we haven't reached the end of the keypath string
        if(index != input.endIndex) {
            Log.log(level: .error, message: "Error parsing KeyPath, KeyPath is invalid.")
            throw TestServerError.badRequest("KeyPath is invalid.")
        }
        
        Log.log(level: .debug, message: "Parsed KeyPath components: \(components)")
        return components
    }
    
    private mutating func parseProperty(first: Bool = false) throws -> KeyPathComponent? {
        if(!first) {
            guard expect(".") else {
                Log.log(level: .error, message: "Error parsing KeyPath, invalid property name in KeyPath.")
                throw TestServerError.badRequest("Invalid property name in KeyPath.")
            }
        }
        
        var property = ""
        while let char = peek(),
                char != ".",
                char != "[",
                char != "]" {
            if char == "\\" {
                advance()
                if peek() == nil { return nil }
            }
            property.append(advance())
        }
        
        guard !property.isEmpty
        else {
            Log.log(level: .error, message: "Error parsing KeyPath, invalid property name in KeyPath")
            throw TestServerError.badRequest("Invalid property name in KeyPath")
        }
        
        return .property(property)
    }
    
    private mutating func parseIndex() throws -> KeyPathComponent? {
        guard expect("[") else { return nil }
        
        var digitsStr = ""
        while let char = peek(), char != "]" {
            digitsStr.append(advance())
        }
        
        for char in digitsStr {
            if(!char.isNumber) {
                Log.log(level: .error, message: "Error parsing KeyPath, KeyPath contains invalid array index.")
                throw TestServerError.badRequest("KeyPath contains invalid array index.")
            }
        }
        
        guard expect("]") else { return nil }
        
        guard !digitsStr.isEmpty, let digits = Int(digitsStr)
        else {
            Log.log(level: .error, message: "Error parsing KeyPath, KeyPath contains invalid array index.")
            throw TestServerError.badRequest("KeyPath contains invalid array index.")
        }
        
        return .index(digits)
    }
    
    private func peek() -> Character? {
        return index < input.endIndex ? input[index] : nil
    }
    
    @discardableResult
    private mutating func advance(by offset: Int = 1) -> Character {
        let result = input[index]
        index = input.index(index, offsetBy: offset)
        return result
    }
    
    private mutating func expect(_ str: String) -> Bool {
        if input[index...].hasPrefix(str) {
            let _ = advance(by: str.count)
            return true
        }
        return false
    }
}
