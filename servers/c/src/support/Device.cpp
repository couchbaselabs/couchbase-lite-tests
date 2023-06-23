#include "Device.h"

#ifdef _MSC_VER
#define NOMINMAX
#include <sstream>
#include <windows.h>
#pragma comment(lib, "ntdll")

// It's a pain to get the actual header, so just add the function def here
extern "C" NTSYSAPI NTSTATUS NTAPI RtlGetVersion(
    _Out_ PRTL_OSVERSIONINFOW lpVersionInformation
);
#endif

#ifdef __ANDROID__
#include <sstream>
#include <sys/system_properties.h>
#endif

#if defined(__linux__) && !defined(__ANDROID__)
#include <fstream>
#include <optional>
#include <regex>
#include <sys/utsname.h>

static std::optional<string> tryKey(const char* filename, string&& key) {
    static const std::regex r("(.*)=(.*)");
    std::ifstream fin(filename);
    if(!fin) {
        return {};
    }

    fin.exceptions(std::ios_base::badbit);
    string line;
    std::smatch match;
    while(std::getline(fin, line)) {
        if(std::regex_match(line, match, r)) {
            if(match[1] == key) {
                return match[2];
            }
        }
    }

    return {};
}

static string getDistroInfo() {
    // os-release is apparently the standard these days
    if(auto os = tryKey("/etc/os-release", "PRETTY_NAME")) {
        return *os;
    }

    if(auto os = tryKey("/usr/lib/os-release", "PRETTY_NAME")) {
        return *os;
    }

    // Fall back to the non-standard lsb-release
    if(auto lsb = tryKey("/etc/lsb-release", "DISTRIB_DESCRIPTION")) {
        return *lsb;
    }

    if(auto lsb = tryKey("/etc/lsb-release", "DISTRIB_ID")) {
        return *lsb;
    }

    // Last resort, use uname
    utsname uts;
    if(uname(&uts) != 0) {
        return "Unknown Linux";
    }

    return string(uts.sysname) + ' ' + uts.release;
}
#endif

std::string ts_support::device::deviceModel() {
#if __ANDROID__
    char product_model_str[PROP_VALUE_MAX];
    __system_property_get("ro.product.model", product_model_str);
    return product_model_str;
#else
    return "";
#endif
}

std::string ts_support::device::osName() {
#if __ANDROID__
    return "Android";
#elif _MSC_VER
    return "Microsoft Windows";
#elif __linux__
    return "Linux";
#else
    return "Unknown OS";
#endif
}

std::string ts_support::device::osVersion() {
#if __ANDROID__
    char sdk_ver_str[PROP_VALUE_MAX];
    __system_property_get("ro.build.version.sdk", sdk_ver_str);
    return sdk_ver_str;
#elif _MSC_VER
    RTL_OSVERSIONINFOW version{};
    version.dwOSVersionInfoSize = sizeof(RTL_OSVERSIONINFOW);
    auto result = RtlGetVersion(&version);
    std::stringstream ss;
    if (result < 0) {
        ss << "Unknown Version";
    } else {
        ss << version.dwMajorVersion << "."
           << version.dwMinorVersion << "."
           << version.dwBuildNumber;
    }
    return ss.str();
#elif __linux__
    return getDistroInfo();
#else
    return "Unknown";
#endif
}

std::string ts_support::device::apiVersion() {
#if __ANDROID__
    char rel_ver_str[PROP_VALUE_MAX];
    __system_property_get("ro.build.version.release", rel_ver_str);
    return sdk_ver_str;
#else
    return "";
#endif
}