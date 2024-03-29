#pragma once

// support
#include "Define.h"

// lib
#include <cstdint>

namespace ts::support::logger {
    enum class LogLevel : uint8_t {
        debug = 0,
        verbose,
        info,
        warning,
        error,
        none
    };

    void init(LogLevel level);

    void log(LogLevel level, const char *format, ...) __printflike(2, 3);
}