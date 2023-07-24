#pragma once

#include "CBLHeader.h"
#include CBL_HEADER(CBLBase.h)

#include <exception>
#include <nlohmann/json.hpp>
#include <string>
#include <sstream>

namespace ts_support::exception {
    class CBLException : public std::exception {
    public:
        explicit CBLException(const CBLError &error);

        [[nodiscard]] const char *what() const noexcept override { return _what.c_str(); }

        [[nodiscard]] const CBLError &error() const { return _error; }

        [[nodiscard]] nlohmann::json json() const;

    private:
        std::string _what;
        CBLError _error;
    };

    class RequestError : public std::logic_error {
    public:
        explicit RequestError(const std::string &s) : logic_error(s) {}

    private:
        std::string _what;
    };
}

static inline void CheckError(CBLError &error) {
    if (error.code > 0) { throw ts_support::exception::CBLException(error); }
}

static inline void CheckNotNull(const void *obj, const std::string &message) {
    if (!obj) { throw std::runtime_error(message); }
}
