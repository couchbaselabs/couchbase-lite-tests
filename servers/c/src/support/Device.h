#pragma once

#include <string>

namespace ts_support::device {
    std::string deviceModel();

    std::string osName();

    std::string osVersion();

    std::string apiVersion();
}