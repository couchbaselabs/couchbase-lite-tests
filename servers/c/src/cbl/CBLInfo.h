#pragma once

#include "CBLHeader.h"
#include CBL_HEADER(CBL_Edition.h)

#include <string>

namespace ts::cbl::cbl_info {
    static std::string version() {
        return CBLITE_VERSION;
    }

    static int build() {
        return CBLITE_BUILD_NUMBER;
    }

    static std::string edition() {
#ifdef COUCHBASE_ENTERPRISE
        return "Enterprise";
#else
        return "Community";
#endif
    }
}
