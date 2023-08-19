#pragma once

#include <string>
#include <sstream>
#include <vector>

namespace ts::support::str {
    template<typename ... Args>
    static std::string concat(const Args &... args) {
        std::stringstream ss;
        int unpack[] = {0, ((void) (ss << args), 0) ...};
        static_cast<void>(unpack);
        return ss.str();
    }

    static std::vector<std::string> split(const std::string &str, char delimeter) {
        std::vector<std::string> elements;
        std::stringstream ss(str);
        std::string item;
        while (std::getline(ss, item, delimeter)) {
            elements.push_back(item);
        }
        return elements;
    }
}