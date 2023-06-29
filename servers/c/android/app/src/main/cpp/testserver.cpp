#include <jni.h>
#include <android/log.h>
#include <string>
#include "TestServer.h"
#include "support/Android.h"

using namespace std;

extern "C"
JNIEXPORT void JNICALL
Java_com_couchbase_lite_testserver_TestServerKt_initAndroidContext(JNIEnv *env, jclass clazz, jstring files_dir, jstring temp_dir, jstring assets_dir) {
    const char *filesDir = env->GetStringUTFChars(files_dir, nullptr);
    const char *tempDir = env->GetStringUTFChars(temp_dir, nullptr);
    const char *assetsDir = env->GetStringUTFChars(assets_dir, nullptr);
    ts_support::android::initAndroidContext({
        string(filesDir),
        string(tempDir),
        string(assetsDir)
    });
    env->ReleaseStringUTFChars(files_dir, filesDir);
    env->ReleaseStringUTFChars(temp_dir, tempDir);
    env->ReleaseStringUTFChars(assets_dir, assetsDir);
}

extern "C"
JNIEXPORT jlong JNICALL
Java_com_couchbase_lite_testserver_TestServer_createServer(JNIEnv *env, [[maybe_unused]] jobject thiz) {
    auto server = new TestServer();
    return (jlong) server;
}

extern "C"
JNIEXPORT void JNICALL
Java_com_couchbase_lite_testserver_TestServer_start([[maybe_unused]] JNIEnv *env, [[maybe_unused]] jobject thiz, jlong jserver) {
    auto server = (TestServer *) jserver;
    server->start();
}

extern "C"
JNIEXPORT void JNICALL
Java_com_couchbase_lite_testserver_TestServer_stop([[maybe_unused]] JNIEnv *env, [[maybe_unused]] jobject thiz, jlong jserver) {
    auto server = (TestServer *) jserver;
    server->stop();
}

extern "C"
JNIEXPORT void JNICALL
Java_com_couchbase_lite_testserver_TestServer_free([[maybe_unused]]JNIEnv *env, [[maybe_unused]]jobject thiz, jlong jserver) {
    auto server = (TestServer *) jserver;
    delete server;
}
