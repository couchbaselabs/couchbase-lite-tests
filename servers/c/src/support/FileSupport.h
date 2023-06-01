#pragma once

#include <string>

namespace ts_support::files {
    std::string tempDir(const std::string &dir, bool create);

    std::string assetDir();
}
