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
    
    public mutating func parse() -> [KeyPathComponent]? {
        var components: [KeyPathComponent] = []
        
        // Skip optional "$."
        if input.hasPrefix("$.") {
            let _ = advance(by: 2)
        }
        
        // Parse first component
        // If there is no first component, this fails
        if let component = parseProperty() ?? parseIndex() {
            components.append(component)
        } else {
            return nil
        }
        
        // Parse any remaining components
        while let component = (peek() == "." ? parseProperty() : parseIndex()) {
            components.append(component)
        }
        
        return components
    }
    
    private mutating func parseProperty() -> KeyPathComponent? {
        guard expect(".") else { return nil }
        
        var property = ""
        while let char = peek(),
                char != ".",
                char != "[",
                char != "]" {
            if char == "\\" {
                let _ = advance()
                if peek() == nil { return nil }
            }
            property.append(advance())
        }
        return .property(property)
    }
    
    private mutating func parseIndex() -> KeyPathComponent? {
        guard expect("[") else { return nil }
        
        var digits = ""
        while let char = peek(), char.isNumber {
            digits.append(advance())
        }
        
        guard expect("]") else { return nil }
        
        return .index(Int(digits) ?? 0)
    }
    
    private func peek() -> Character? {
        return index < input.endIndex ? input[index] : nil
    }
    
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
