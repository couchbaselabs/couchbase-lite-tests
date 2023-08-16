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
        self.index = input.startIndex
    }
    
    public mutating func parse() throws -> [KeyPathComponent]? {
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
            throw TestServerError.badRequest("First KeyPath component should be a property.")
        }
        
        // Parse any remaining components
        while let component = (peek() == "." ? try parseProperty() : peek() == "[" ? try parseIndex() : nil) {
            components.append(component)
        }
        
        // We can't parse any more valid components, but we haven't reached the end of the keypath string
        if(index != input.endIndex) {
            throw TestServerError.badRequest("KeyPath '\(input)' is invalid.")
        }
        
        return components
    }
    
    private mutating func parseProperty(first: Bool = false) throws -> KeyPathComponent? {
        if(!first) {
            guard expect(".") else { throw TestServerError.badRequest("KeyPath '\(input)' is invalid.") }
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
            throw TestServerError.badRequest("KeyPath '\(input)' is invalid.")
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
                throw TestServerError.badRequest("KeyPath '\(input)' contains invalid array index.")
            }
        }
        
        guard expect("]") else { return nil }
        
        guard !digitsStr.isEmpty, let digits = Int(digitsStr)
        else {
            throw TestServerError.badRequest("KeyPath '\(input)' contains invalid array index.")
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
