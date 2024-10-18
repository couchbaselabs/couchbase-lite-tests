#pragma once

#include "Dispatcher.h"
#include "Request.h"

// cbl
#include "CBLManager.h"
#include "CollectionSpec.h"

// support
#include "Defer.h"
#include "Define.h"
#include "Error.h"
#include "Fleece.h"
#include "JSON.h"
#include "Log.h"
#include "Precondition.h"
#include "StringUtil.h"

// lib
#include <string>
#include <cstring>
#include <sstream>

using namespace nlohmann;
using namespace ts;
using namespace ts::cbl;
using namespace ts::support;
using namespace ts::support::error;
using namespace ts::support::logger;
using namespace ts::support::precond;
using namespace ts::support::json_util;
using namespace ts::support::str;
using namespace std;

namespace ts {
    enum class UpdateDatabaseType {
        update, del, purge
    };

    static auto UpdateDatabaseTypeEnum = StringEnum<UpdateDatabaseType>(
        {
            "update",
            "delete",
            "purge"
        },
        {
            UpdateDatabaseType::update,
            UpdateDatabaseType::del,
            UpdateDatabaseType::purge
        }
    );
}
