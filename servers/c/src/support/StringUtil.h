#pragma once

#include <string>
#include <vector>
#include <sstream>

namespace ts::support::str {
    template<typename ... Args>
    std::string concat(const Args &... args) {
        std::stringstream ss;
        int unpack[] = {0, ((void) (ss << args), 0) ...};
        static_cast<void>(unpack);
        return ss.str();
    }

    std::vector<std::string> split(const std::string &str, char delimeter);
}