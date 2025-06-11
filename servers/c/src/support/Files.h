#pragma once

#include <string>

namespace ts::support::files {
    /* Working directory */
    std::string filesDir(const std::string &subdir, bool create);

    /* Assets directory containing artifacts built with binary */
    std::string assetsDir();
}
