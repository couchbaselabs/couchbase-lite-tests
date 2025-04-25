#include "Files.h"

// support
#ifdef __ANDROID__
#include "Android.h"
#endif

#ifdef _WIN32
#include <windows.h>
#elif __linux__
#include <unistd.h>
#endif

// lib
#include <string>
#include <filesystem>

using namespace std;

#ifdef __ANDROID__
using namespace ts::support::android;
#endif

namespace ts::support {
    std::string getExecutablePath() {
#ifdef _WIN32
        char path[MAX_PATH];
        GetModuleFileNameA(nullptr, path, MAX_PATH);
        DWORD result = GetModuleFileNameA(nullptr, path, MAX_PATH);
        if (result == 0) {
            DWORD error = GetLastError();
            throw std::runtime_error("GetModuleFileNameA failed with error code: " + std::to_string(error));
        } else if (result == MAX_PATH) {
            throw std::runtime_error("Path is too long and was truncated.");
        }
        
        return std::string(path);
#elif __linux__
        char path[1024];
        ssize_t count = readlink("/proc/self/exe", path, sizeof(path));
        if (count != -1) {
            return std::string(path, count);
        } else {
            throw std::runtime_error("Failed to get executable path");
        }
#else
        throw std::runtime_error("Unsupported platform");
#endif
}

    string files::filesDir(const string &subdir, bool create) {
#ifdef WIN32
        auto curPath = filesystem::current_path();
        string dir = subdir.empty() ? curPath.string() : (curPath / subdir).string();
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
        auto current = filesystem::path(getExecutablePath()).parent_path() / ".." / "assets";
        return current.string();
    }
}