#pragma once

#include "Error.h"
#include <stdexcept>
#include <string>

namespace ts::support::precond {
    static inline void checkNotNull(const void *obj, const std::string &message) {
        if (!obj) { throw std::logic_error(message); }
    }

    static inline void checkCBLError(CBLError &error) {
        if (error.code > 0) { throw error::CBLException(error); }
    }
}