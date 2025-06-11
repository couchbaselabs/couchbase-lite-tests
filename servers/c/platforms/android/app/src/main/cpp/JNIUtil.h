#pragma once

#include <jni.h>

namespace ts::jni {
    JNIEnv* getJNIEnv(bool* didAttach = nullptr);
    void detachCurrentThread();

    jclass fileDownloaderClass();
    jmethodID fileDownloaderDownloadMethod();
}