#pragma once

#include <string>

namespace file_support {
    std::string tempDir(const std::string &dir, bool create);

    std::string assetDir();
}
