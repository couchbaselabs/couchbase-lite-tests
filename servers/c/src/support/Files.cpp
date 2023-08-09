#include "Files.h"

// support
#ifdef __ANDROID__
#include "Android.h"
#endif

// lib
#include <string>
#include <filesystem>

using namespace std;

#ifdef __ANDROID__
using namespace ts::support::android;
#endif

namespace ts::support {
    string files::filesDir(const string &subdir, bool create) {
#ifdef WIN32
        string dir = subdir.empty() ? "C:\\tmp" : "C:\\tmp\\" + subdir;
#else
#ifdef __ANDROID__
        string dir = subdir.empty() ? androidContext()->filesDir : androidContext()->filesDir + "/" + subdir;
#else
        string dir = subdir.empty() ? "/tmp" : "/tmp/" + subdir;
#endif
#endif

        if (create) {
            filesystem::create_directory(dir);
        }
        return dir;
    }

    string files::assetsDir() {
#ifdef __ANDROID__
        return androidContext()->assetsDir;
#endif
        auto current = filesystem::current_path() / "assets";
        return current.generic_string();
    }
}