#pragma once

#include <string>

namespace test_server_support {
    std::string tempDir(const std::string &dir, bool create);

    std::string assetDir();
}
