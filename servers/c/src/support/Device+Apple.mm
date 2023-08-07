#include "Device.h"
#import <Foundation/Foundation.h>

#pragma clang diagnostic push
#pragma ide diagnostic ignored "IncompatibleTypes"

using namespace std;

#if TARGET_OS_IPHONE && !TARGET_OS_SIMULATOR
#include <sys/utsname.h>
static string getDeviceModel(const char *fallback) {
    utsname uts;
    if (uname(&uts) != 0) {
        return fallback;
    }
    return uts.machine;
}
#endif

static string getOSVersion() {
    return [[[NSProcessInfo processInfo] operatingSystemVersionString] cStringUsingEncoding:NSASCIIStringEncoding];
}

string ts::support::device::deviceModel() {
#if TARGET_IPHONE_SIMULATOR
    return "iOS Simulator";
#elif TARGET_OS_IPHONE
    return getDeviceModel("iOS Device");
#elif TARGET_OS_MAC
    return "";
#else
    return "Unknown Apple Device";
#endif
}

string ts::support::device::osName() {
#if TARGET_IPHONE_SIMULATOR || TARGET_OS_IPHONE
    return "iOS";
#elif TARGET_OS_MAC
    return "macOS";
#else
    return "Unknown Apple OS";
#endif
}

string ts::support::device::osVersion() {
#if TARGET_IPHONE_SIMULATOR || TARGET_OS_IPHONE || TARGET_OS_MAC
    return getOSVersion();
#else
    return "Unknown Version";
#endif
}

string ts::support::device::apiVersion() {
    return "";
}

#pragma clang diagnostic pop
