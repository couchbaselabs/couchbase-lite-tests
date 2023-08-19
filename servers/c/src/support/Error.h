#pragma once

#include "CBLHeader.h"
#include CBL_HEADER(CBLBase.h)

#include <nlohmann/json.hpp>
#include <stdexcept>
#include <string>
#include <sstream>

namespace ts::support::error {
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
    };
}