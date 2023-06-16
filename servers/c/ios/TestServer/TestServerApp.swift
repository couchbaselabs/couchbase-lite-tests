//
//  TestServerApp.swift
//  TestServer
//
//  Created by Pasin Suriyentrakorn on 6/15/23.
//

import SwiftUI

@main
struct TestServerApp: App {
    @Environment(\.scenePhase) private var scenePhase
    
    let server = CBLTestServer()
    
    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .onChange(of: scenePhase) { (phase) in
            switch phase {
            case .active:
                server.start()
            case .background:
                server.stop()
            default:
                break
            }
        }
    }
}
