#pragma once

#include <string>

namespace ts_support::files {
    std::string filesDir(const std::string &subdir, bool create);

    std::string assetsDir();
}
