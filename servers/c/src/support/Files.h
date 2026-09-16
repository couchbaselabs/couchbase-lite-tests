#pragma once

#include <string>

namespace ts::support::files {
    /* Working directory */
    std::string filesDir(const std::string &subdir, bool create);

    /* Creates dir and any missing parents if needed, and returns it */
    std::string ensureDir(const std::string &dir);

    /* Assets directory containing artifacts built with binary */
    std::string assetsDir();
}
