#include "Files.h"

#ifdef __ANDROID__
#include "Android.h"
#endif

#include <string>
#include <filesystem>

using namespace std;

#ifdef __ANDROID__
using namespace ts_support::android;
#endif

string ts_support::files::filesDir(const string &subdir, bool create) {
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

string ts_support::files::assetsDir() {
#ifdef __ANDROID__
    return androidContext()->assetsDir;
#endif
    auto current = filesystem::current_path() / "assets";
    return current.generic_string();
}