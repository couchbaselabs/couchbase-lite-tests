//
//  CBL_Tests_iOSApp.swift
//  CBL-Tests-iOS
//
//  Created by Callum Birks on 01/08/2023.
//

import SwiftUI

@main
struct CBL_Tests_iOSApp: App {
    let testServer: TestServer
    
    init() {
        testServer = TestServer(port: 80)
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
