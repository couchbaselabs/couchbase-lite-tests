#pragma once

#include "support/Defer.h"
#include "support/Exception.h"
#include "cbl/CouchbaseLite.h"

// FLString from std::string
#define FLS(str) FLStr(str.c_str())

// std::string from FLString
#define STR(str) std::string(static_cast<const char *>(str.buf), str.size)

inline void checkError(CBLError &error) {
    if (error.code > 0) { throw CBLException(error); }
}
