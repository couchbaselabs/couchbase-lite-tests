#pragma once

#include <exception>
#include <string>
#include <sstream>
#include "cbl/CBLBase.h"

using namespace std;

class CBLException : public std::exception {
public:
    explicit CBLException(const CBLError &error) {
        _error = error;

        FLSliceResult messageVal = CBLError_Message(&error);
        auto message = string(static_cast<const char *>(messageVal.buf), messageVal.size);

        stringstream ss;
        ss << "Couchbase Lite Error : " << (int) error.domain << "/" << error.code << ", " << message;
        _what = ss.str();
    }

    [[nodiscard]]
    const char *what() const noexcept override {
        return _what.c_str();
    }

    const CBLError &error() const {
        return _error;
    }

private:
    string _what;
    CBLError _error;
};
