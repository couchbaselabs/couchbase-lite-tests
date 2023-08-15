#include "TestServer.h"

// cbl
#include "CBLInfo.h"

// support
#include "Files.h"

// lib
#include <iostream>
#include <thread>

using namespace std;
using namespace ts;
using namespace ts::cbl;
using namespace ts::support::files;

int main() {
    try {
        TestServer::init();

        TestServer server = TestServer();
        server.start();

        cout << "Using CBL-C " << cbl_info::version() << "-" << cbl_info::build();
        cout << " (" << cbl_info::edition() << ")" << endl;
        cout << "Listening on port " << TestServer::PORT << "..." << endl;

        while (true) {
            std::this_thread::sleep_for(1s);
        }
    } catch (const exception &e) {
        cerr << "Error: " << e.what() << endl;
        return -1;
    }
}
