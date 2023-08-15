import UIKit

@main
class AppDelegate: UIResponder, UIApplicationDelegate {
    var server: TSTestServer!
    var ipAddressServer: IPAddressServer!
    
    func application(_ application: UIApplication, didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?) -> Bool {
        TSTestServer.initialize()
        
        self.server = TSTestServer()
        self.server.start()
        
        ipAddressServer = IPAddressServer()
        ipAddressServer.start()
        
        return true
    }

    // MARK: UISceneSession Lifecycle

    func application(_ application: UIApplication, configurationForConnecting connectingSceneSession: UISceneSession, options: UIScene.ConnectionOptions) -> UISceneConfiguration {
        return UISceneConfiguration(name: "Default Configuration", sessionRole: connectingSceneSession.role)
    }

    func application(_ application: UIApplication, didDiscardSceneSessions sceneSessions: Set<UISceneSession>) { }
}
