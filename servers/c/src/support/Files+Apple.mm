#import "Files.h"
#import <Foundation/Foundation.h>
#include <filesystem>
#include <mach-o/dyld.h>
#include <sys/stat.h>

#pragma clang diagnostic push
#pragma ide diagnostic ignored "IncompatibleTypes"

using namespace std;


namespace ts::support {
    std::string getExecutablePath() {
        char path[1024];
        uint32_t size = sizeof(path);
        if (_NSGetExecutablePath(path, &size) == 0) {
            return std::string(path);
        } else {
            throw std::runtime_error("Buffer too small for executable path");
        }
    }

    string files::filesDir(const std::string &subdir, bool create) {
        NSString *tempDir = NSTemporaryDirectory();
        if (!subdir.empty()) {
            NSString *sub = [NSString stringWithCString:subdir.c_str() encoding:NSUTF8StringEncoding];
            tempDir = [tempDir stringByAppendingPathComponent:sub];
        }
        if (create && mkdir(tempDir.UTF8String, 0744) != 0 && errno != EEXIST) {
            throw std::runtime_error("Cannot create temp director, errno = " + to_string(errno));
        }
        return tempDir.UTF8String;
    }

    string files::assetsDir() {
        // TODO: The identifier should be passed into the function instead of hard coding the value here.
        auto bundle = CFBundleGetBundleWithIdentifier(CFSTR("com.couchbase.CBLTestServer"));
        if (bundle) {
            auto url = CFBundleCopyResourcesDirectoryURL(bundle);
            CFAutorelease(url);
            url = CFURLCopyAbsoluteURL(url);
            CFAutorelease(url);
            auto path = CFURLCopyFileSystemPath(url, kCFURLPOSIXPathStyle);
            CFAutorelease(path);
            char pathBuf[1000];
            CFStringGetCString(path, pathBuf, sizeof(pathBuf), kCFStringEncodingUTF8);
            return pathBuf;
        } else {
            auto current = filesystem::path(getExecutablePath()).parent_path() / ".." / "assets";
            return current.string();
        }
    }
}

#pragma clang diagnostic pop
