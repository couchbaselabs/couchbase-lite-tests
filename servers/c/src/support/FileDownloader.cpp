#include "FileDownloader.h"

#if defined(_WIN32)
#include <urlmon.h>
#pragma comment(lib, "urlmon.lib")
#elif defined(__ANDROID__)
#include <JNIUtil.h>
#elif defined(__linux__)
#include <fstream>
#include <ixwebsocket/IXHttpClient.h>
#endif

namespace ts::support {
    void FileDownloader::download(const std::string &url, const std::string &destinationPath) {
#if defined(_WIN32)
        HRESULT hr = URLDownloadToFileA(nullptr, url.c_str(), destinationPath.c_str(), 0, nullptr);
        if (FAILED(hr)) {
            throw std::runtime_error("Failed to download file from URL '" + url + "' : " + std::to_string(hr));
        }
#elif defined(__ANDROID__)
        bool didAttach = false;
        JNIEnv* env = ts::jni::getJNIEnv(&didAttach);
        if (!env) {
            throw std::runtime_error("Cannot get JNI environment");
        }

        jclass cls = ts::jni::fileDownloaderClass();
        jmethodID mid = ts::jni::fileDownloaderDownloadMethod();
        if (!cls || !mid) {
            throw std::runtime_error("FileDownloader JNI references not initialized");
        }

        jstring jurl = env->NewStringUTF(url.c_str());
        jstring jdest = env->NewStringUTF(destinationPath.c_str());
        env->CallStaticVoidMethod(cls, mid, jurl, jdest);

        env->DeleteLocalRef(jurl);
        env->DeleteLocalRef(jdest);

        jboolean hasError = env->ExceptionCheck();
        if (hasError) {
            env->ExceptionDescribe();
            env->ExceptionClear();
        }

        if (didAttach) {
            ts::jni::detachCurrentThread();
        }

        if (hasError) {
            throw std::runtime_error("Failed to download file from URL '" + url + "'");
        }
#elif defined(__linux__)
        ix::HttpClient httpClient;

        ix::SocketTLSOptions tlsOptions;
        tlsOptions.caFile = "SYSTEM";
        httpClient.setTLSOptions(tlsOptions);

        auto args = httpClient.createRequest(url);
        auto response = httpClient.get(url, args);
        if (response->statusCode == 200) {
            std::ofstream outFile(destinationPath, std::ios::binary);
            if (outFile.is_open()) {
                outFile << response->body;
            } else {
                throw std::runtime_error("Unable to save downloaded file at " + destinationPath);
            }
        } else {
            throw std::runtime_error("Failed to download file from URL '" + url + "' : " + std::to_string(response->statusCode));
        }
#else
        throw std::runtime_error("Failed to download file from URL '" + url + "' : Unsupported Platform");
#endif
    }
}