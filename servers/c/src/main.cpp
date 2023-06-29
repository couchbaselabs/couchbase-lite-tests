#include <iostream>
#include <thread>

#include <civetweb.h>
#include "cbl/CouchbaseLite.h"

#include "support/Files.h"
#include "TestServer.h"

using namespace std;
using namespace ts_support::files;

int main() {
    try {
        mg_init_library(0);

        TestServer server = TestServer();
        server.start();

        cout << "Using CBL C version " << CBLITE_VERSION << "-" << CBLITE_BUILD_NUMBER;
#ifdef COUCHBASE_ENTERPRISE
        cout << " (Enterprise)";
#endif
        cout << endl;
        cout << "Listening on port " << TestServer::PORT << "..." << endl;

        while (true) {
            std::this_thread::sleep_for(1s);
        }
    } catch (const exception &e) {
        cerr << "Error: " << e.what() << endl;
        return -1;
    }
}
