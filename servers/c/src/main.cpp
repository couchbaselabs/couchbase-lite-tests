#include <iostream>
#include <thread>

#include <civetweb.h>

#include "CBLManager.h"
#include "support/Files.h"
#include "TestServer.h"

using namespace std;
using namespace ts_support::files;

int main() {
    try {
        mg_init_library(0);

        TestServer server = TestServer();
        server.start();

        cout << "Using CBL-C " << CBLManager::version() << "-" << CBLManager::buildNumber();
        cout << " (" << CBLManager::edition() << ")" << endl;
        cout << "Listening on port " << TestServer::PORT << "..." << endl;

        while (true) {
            std::this_thread::sleep_for(1s);
        }
    } catch (const exception &e) {
        cerr << "Error: " << e.what() << endl;
        return -1;
    }
}
