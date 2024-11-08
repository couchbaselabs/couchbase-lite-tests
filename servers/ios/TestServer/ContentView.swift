//
//  ContentView.swift
//  TestServer
//
//  Created by Callum Birks on 01/08/2023.
//

import SwiftUI

struct ContentView: View {
    var body: some View {
        VStack {
            Image(systemName: "globe")
                .imageScale(.large)
                .foregroundStyle(.tint)
            Text(IPAddress.shared.address)
                .padding()
        }
        .padding()
    }
}

// Disable directive Preview as it is not recongized by XCode 14:
//#Preview {
//    ContentView()
//}
