#pragma once

#include <stdexcept>
#include <optional>
#include <string>
#include <vector>

namespace ts_support::keypath {
    struct Path {
        std::optional<std::string> key;  ///< Dict key, or no key
        std::optional<size_t> index;     ///< Array index, only if no key
    };

    class KeyPathError : public std::logic_error {
    public:
        explicit KeyPathError(const std::string &keyPath, const std::string &reason)
                : logic_error("Invalid key path '" + keyPath + "' : " + reason) {}
    };

    std::vector<Path> parseKeyPath(const std::string &keyPath);
}
