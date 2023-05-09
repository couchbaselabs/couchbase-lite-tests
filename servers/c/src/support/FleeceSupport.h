#pragma once

#include "fleece/Fleece.h"
#include <nlohmann/json.hpp>

namespace fleece_support {
    void setSlotValue(FLSlot slot, const nlohmann::json &json);
}