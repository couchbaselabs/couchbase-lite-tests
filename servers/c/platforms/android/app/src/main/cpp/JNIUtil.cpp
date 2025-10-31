#include "JNIUtil.h"
#include <stdexcept>

namespace ts::jni {
    static JavaVM* g_JavaVM;
    static jclass g_FileDownloaderClass;
    static jmethodID g_DownloadMethod;

    JNIEnv* getJNIEnv(bool* didAttach) {
        if (!g_JavaVM) {
            return nullptr;
        }

        JNIEnv* env = nullptr;
        jint result = g_JavaVM->GetEnv(reinterpret_cast<void**>(&env), JNI_VERSION_1_6);

        if (result == JNI_OK) {
            if (didAttach) *didAttach = false;
            return env;
        }

        if (result == JNI_EDETACHED) {
            if (g_JavaVM->AttachCurrentThread(&env, nullptr) == 0) {
                if (didAttach) *didAttach = true;
                return env;
            }
        }
        return nullptr;
    }

    void detachCurrentThread() {
        if (g_JavaVM) {
            g_JavaVM->DetachCurrentThread();
        }
    }

    jclass fileDownloaderClass() {
        return g_FileDownloaderClass;
    }

    jmethodID fileDownloaderDownloadMethod() {
        return g_DownloadMethod;
    }

    bool init(JNIEnv* env) {
        jclass localClass = env->FindClass("com/couchbase/lite/testserver/util/FileDownloader");
        if (!localClass) {
            return false;
        }

        g_FileDownloaderClass = reinterpret_cast<jclass>(env->NewGlobalRef(localClass));
        env->DeleteLocalRef(localClass);
        if (!g_FileDownloaderClass) {
            return false;
        }

        g_DownloadMethod = env->GetStaticMethodID(g_FileDownloaderClass, "download", "(Ljava/lang/String;Ljava/lang/String;)V");
        return (g_DownloadMethod != nullptr);
    }

    void cleanup() {
        JNIEnv* env = getJNIEnv();
        if (env && g_FileDownloaderClass) {
            env->DeleteGlobalRef(g_FileDownloaderClass);
        }
        g_FileDownloaderClass = nullptr;
        g_DownloadMethod = nullptr;
    }
}

extern "C"
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM* vm, void*) {
    ts::jni::g_JavaVM = vm;

    JNIEnv* env = ts::jni::getJNIEnv();
    if (!env) {
        return JNI_ERR;
    }

    if (!ts::jni::init(env)) {
        return JNI_ERR;
    }

    return JNI_VERSION_1_6;
}

extern "C"
JNIEXPORT void JNICALL JNI_OnUnload(JavaVM*, void*) {
    ts::jni::cleanup();
}