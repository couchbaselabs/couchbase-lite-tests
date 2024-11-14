#pragma once

#include "Define.h"

#include <cstdint>
#include <cstdarg>
#include <memory>

namespace ts::log {
    enum class LogLevel : uint8_t {
        debug = 0,
        verbose,
        info,
        warning,
        error,
        none
    };

    constexpr const char *logLevelNames[] = {"DEBUG", "VERBOSE", "INFO", "WARNING", "ERROR",
                                             "NONE"};

    class Logger {
    public:
        virtual ~Logger() = default;
        
        virtual void log(LogLevel level, const char *domain, const char *message) = 0;

        virtual void close() = 0;
    };

    class Log {
    public:
        static void init(LogLevel level);

        static void useDefaultLogger();

        static void useCustomLogger(std::shared_ptr<Logger> customLogger);

        static void log(LogLevel level, const char *format, ...) __printflike(2, 3);

        static void logToConsole(LogLevel level, const char *format, ...) __printflike(2, 3);
    };
}
