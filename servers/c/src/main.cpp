#include <iostream>
#include <thread>

#include <civetweb.h>
#include "cbl/CouchbaseLite.h"

#include "support/FileSupport.h"
#include "TestServer.h"

using namespace std;
using namespace file_support;

int main() {
    mg_init_library(0);
    TestServer::Context context = {file_support::tempDir("CBL-C-TestServer", true),
                                   file_support::assetDir()};
    TestServer server = TestServer(context);
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
}
