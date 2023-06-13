#pragma once

#include "fleece/Fleece.h"
#include <nlohmann/json.hpp>

namespace ts_support::fleece {
    void setSlotValue(FLSlot slot, const nlohmann::json &json);
}
