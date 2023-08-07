#pragma once

#include <string>

namespace ts::support::device {
    std::string deviceModel();

    std::string osName();

    std::string osVersion();

    std::string apiVersion();
}