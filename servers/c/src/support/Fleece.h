#pragma once

#ifdef __APPLE__
#include <TargetConditionals.h>
#if !TARGET_OS_OSX
#include "CouchbaseLite/Fleece.h"
#else
#include "fleece/Fleece.h"
#endif
#else
#include "fleece/Fleece.h"
#endif

#include <nlohmann/json.hpp>

namespace ts_support::fleece {
    void setSlotValue(FLSlot slot, const nlohmann::json &json);
}
