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

struct Options {
    unsigned short port{TestServer::DEFAULT_PORT};
    string filesDir;
};

static void usage(const char *prog) {
    cerr << "Usage: " << prog << " [--port <port>] [--files-dir <dir>]" << endl;
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

static Options parseArgs(int argc, char **argv) {
    Options options;
    for (int i = 1; i < argc; i++) {
        const string arg = argv[i];
        if (arg == "--port") {
            if (++i >= argc) { throw invalid_argument("Missing value for --port"); }
            options.port = parsePort(argv[i]);
        } else if (arg == "--files-dir") {
            if (++i >= argc) { throw invalid_argument("Missing value for --files-dir"); }
            options.filesDir = argv[i];
            if (options.filesDir.empty()) {
                throw invalid_argument("Invalid --files-dir value: the directory cannot be empty");
            }
        } else {
            throw invalid_argument("Unknown argument: " + arg);
        }
    }
    return options;
}

int main(int argc, char **argv) {
    Options options;
    try {
        options = parseArgs(argc, argv);
    } catch (const exception &e) {
        cerr << "Error: " << e.what() << endl;
        usage(argv[0]);
        return 1;
    }

    try {
        TestServer::init();

        TestServer server = TestServer(options.port, options.filesDir);
        server.start();

        cout << "Using CBL-C " << cbl_info::version() << "-" << cbl_info::build();
        cout << " (" << cbl_info::edition() << ")" << endl;
        cout << "Using files directory " << server.context().filesDir << endl;
        cout << "Listening on port " << server.port() << "..." << endl;

        while (true) {
            std::this_thread::sleep_for(1s);
        }
    } catch (const exception &e) {
        cerr << "Error: " << e.what() << endl;
        return -1;
    }
}
