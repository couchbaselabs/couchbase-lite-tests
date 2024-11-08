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
        DatabaseManager.InitializeShared()
        if let databaseManager = DatabaseManager.shared {
            IPAddress.shared.advertise()
            testServer = TestServer(port: 8080, dbManager: databaseManager)
            Task { [weak testServer] in
                await testServer?.run()
            }
        } else {
            fatalError("Failed to initialize DatabaseManager singleton!")
        }
    }
    
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
