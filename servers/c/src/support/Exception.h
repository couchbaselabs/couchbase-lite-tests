#pragma once

#include "CBLHeader.h"
#include CBL_HEADER(CBLBase.h)

#include <exception>
#include <string>
#include <sstream>

using namespace std;

namespace ts_support::exception {
    class CBLException : public std::exception {
    public:
        explicit CBLException(const CBLError &error);

        [[nodiscard]] const char *what() const noexcept override { return _what.c_str(); }

        [[nodiscard]] const CBLError &error() const { return _error; }

        [[nodiscard]] std::string json() const;

    private:
        string _what;
        CBLError _error;
    };
}

static inline void CheckError(CBLError &error) {
    if (error.code > 0) { throw ts_support::exception::CBLException(error); }
}

static inline void CheckNotNull(const void *obj, const string &message) {
    if (!obj) { throw runtime_error(message); }
}
