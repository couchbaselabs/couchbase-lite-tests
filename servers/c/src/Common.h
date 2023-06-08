#pragma once

#include "support/Defer.h"
#include "support/Define.h"
#include "support/Exception.h"
#include "cbl/CouchbaseLite.h"

using namespace ts_support::exception;

static inline void CheckError(CBLError &error) {
    if (error.code > 0) { throw CBLException(error); }
}

static inline void CheckNotNull(void *obj, const string &message) {
    if (!obj) { throw runtime_error(message); }
}
