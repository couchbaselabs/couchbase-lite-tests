#pragma once

#include "CBLHeader.h"
#include FLEECE_HEADER(Fleece.h)

#include <nlohmann/json.hpp>

namespace ts_support::fleece {
    nlohmann::json toJSON(FLValue value);
    
    void updateProperties(FLMutableDict dict, FLSlice keyPath, const nlohmann::json &value);

    void removeProperties(FLMutableDict dict, FLSlice keyPath);

    FLDict compareDicts(FLDict dict1, FLDict dict2);
}
