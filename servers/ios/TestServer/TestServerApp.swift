//
//  TestServerApp.swift
//  TestServer
//
//  Created by Callum Birks on 01/08/2023.
//


import SwiftUI

@main
struct TestServerApp: App {
    let testServer: TestServer
    
    init() {
        IPAddress.shared.advertise()
        testServer = TestServer(port: 8080)
        Task { [weak testServer] in
            await testServer?.run()
        }
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
