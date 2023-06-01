#include "FileSupport.h"

#include <string>
#include <filesystem>
#include <iostream>

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
#else
    string dir = subdir.empty() ? "/tmp" : "/tmp/" + subdir;
#endif

    if (create) {
        filesystem::create_directory(dir);
    }
    return dir;
}

string test_server_support::assetDir() {
#ifdef __ANDROID__
    // TODO:
    return ""
#endif
        auto current = filesystem::current_path() / "assets";
        return current.generic_string();
}