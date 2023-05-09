#pragma once

#include "support/Defer.h"
#include "support/Define.h"
#include "support/Exception.h"
#include "cbl/CouchbaseLite.h"

inline void checkError(CBLError &error) {
    if (error.code > 0) { throw CBLException(error); }
}

inline void checkNotNull(void *obj, const char *message) {
    if (!obj) { throw runtime_error(message); }
}
