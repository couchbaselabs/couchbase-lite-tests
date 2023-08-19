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
using namespace ts::support::precond;
using namespace ts::support::json_util;
using namespace ts::support::str;
using namespace std;

static inline void CheckBody(const json &body) {
    if (!body.is_object()) {
        throw RequestError("Request body is not json object");
    }
}

static inline bool EnumEquals(const string &enum1, const string &enum2) {
    return strcasecmp(enum1.c_str(), enum2.c_str()) == 0;
}

static constexpr const char *kUpdateDatabaseTypeUpdate = "UPDATE";
static constexpr const char *kUpdateDatabaseTypeDelete = "DELETE";
static constexpr const char *kUpdateDatabaseTypePurge = "PURGE";
