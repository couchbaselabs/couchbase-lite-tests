#include "FileSupport.h"

#include <string>

#ifndef _MSC_VER

#include <sys/stat.h>

#endif

using namespace std;

string test_server_support::tempDir(const string &subdir, bool create) {
#ifdef __ANDROID__
    // TODO:
    return ""
#endif

#ifdef WIN32
    string dir = subdir.empty() ? "C:\\tmp" : "C:\\tmp\\" + subdir;
    if (create && _mkdir(dir.c_str()) != 0 && errno != EEXIST) {
        throw std::runtime_error("Cannot create temp director, errno = " + to_string(errno));
    }
    return dir;
#else
    string dir = subdir.empty() ? "/tmp" : "/tmp/" + subdir;
    if (create && mkdir(dir.c_str(), 0744) != 0 && errno != EEXIST) {
        throw std::runtime_error("Cannot create temp director, errno = " + to_string(errno));
    }
    return dir;
#endif
}

string test_server_support::assetDir() {
#ifdef __ANDROID__
    // TODO:
    return ""
#endif
    return "assets";
}