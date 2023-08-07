#pragma once

#ifdef __ANDROID__

#include <string>

namespace ts::support::android {
    struct AndroidContext {
        std::string filesDir;
        std::string tempDir;
        std::string assetsDir;
    };

    void initAndroidContext(const AndroidContext &context);

    const AndroidContext *androidContext();
}

#endif
