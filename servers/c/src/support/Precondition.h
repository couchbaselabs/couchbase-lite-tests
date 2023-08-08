#pragma once

#include <stdexcept>
#include <string>

namespace ts::support {
    static inline void CheckNotNull(const void *obj, const std::string &message) {
        if (!obj) { throw std::logic_error(message); }
    }
}