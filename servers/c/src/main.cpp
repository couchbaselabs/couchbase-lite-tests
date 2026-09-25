#include "TestServer.h"

// cbl
#include "CBLInfo.h"

// support
#include "Files.h"

// lib
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
#include <chrono>

using namespace std;
using namespace ts;
using namespace ts::cbl;
using namespace ts::support::files;
using namespace std::chrono_literals;

static void usage(const char *prog) {
    cerr << "Usage: " << prog << " [--port <port>]" << endl;
}

static unsigned short parsePort(const string &value) {
    size_t pos = 0;
    long port = 0;
    try { port = stol(value, &pos); }
    catch (const exception &) { pos = 0; }

    // stol stops at the first character it cannot use, so pos also rejects things like "8080x".
    if (pos != value.size() || port < 1 || port > 65535) {
        throw invalid_argument("Invalid --port value: \"" + value + "\" (expected an integer in 1..65535)");
    }
    return static_cast<unsigned short>(port);
}

static unsigned short parseArgs(int argc, char **argv) {
    unsigned short port = TestServer::DEFAULT_PORT;
    for (int i = 1; i < argc; i++) {
        const string arg = argv[i];
        if (arg == "--port") {
            if (++i >= argc) { throw invalid_argument("Missing value for --port"); }
            port = parsePort(argv[i]);
        } else {
            throw invalid_argument("Unknown argument: " + arg);
        }
    }
    return port;
}

int main(int argc, char **argv) {
    unsigned short port;
    try {
        port = parseArgs(argc, argv);
    } catch (const exception &e) {
        cerr << "Error: " << e.what() << endl;
        usage(argv[0]);
        return 1;
    }

    try {
        TestServer::init();

        TestServer server = TestServer(port);
        server.start();

        cout << "Using CBL-C " << cbl_info::version() << "-" << cbl_info::build();
        cout << " (" << cbl_info::edition() << ")" << endl;
        cout << "Listening on port " << server.port() << "..." << endl;

        while (true) {
            std::this_thread::sleep_for(1s);
        }
    } catch (const exception &e) {
        cerr << "Error: " << e.what() << endl;
        return -1;
    }
}
