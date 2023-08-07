#ifdef __ANDROID__

#include "Android.h"
#include "Exception.h"

#include "CBLHeader.h"
#include CBL_HEADER(CouchbaseLite.h)

#include <assert.h>

using namespace ts_support::android;

static AndroidContext sContext;

void ts::support::android::initAndroidContext(const AndroidContext &context) {
    assert(!context.filesDir.empty());
    assert(!context.tempDir.empty());
    assert(!context.assetsDir.empty());

    sContext = context;

    CBLInitContext init{
            .filesDir = sContext.filesDir.c_str(),
            .tempDir = sContext.tempDir.c_str()
    };
    CBLError err{};
    CBL_Init(init, &err);
    CheckError(err);
}

const AndroidContext *ts::support::android::androidContext() {
    if (sContext.filesDir.empty()) {
        return nullptr;
    }
    return &sContext;
}

#endif