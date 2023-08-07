#pragma once

#include <string>

namespace ts::support::files {
    std::string filesDir(const std::string &subdir, bool create);

    std::string assetsDir();
}
