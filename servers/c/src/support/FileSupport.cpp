#include "FileSupport.h"

#include <string>
#include <filesystem>

using namespace std;

string file_support::tempDir(const string &subdir, bool create) {
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

string file_support::assetDir() {
#ifdef __ANDROID__
    // TODO:
    return ""
#endif
    auto current = filesystem::current_path() / "assets";
    return current.generic_string();
}