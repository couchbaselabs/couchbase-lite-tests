#pragma once

#include "CBLHeader.h"
#include FLEECE_HEADER(Fleece.h)

#include <nlohmann/json.hpp>

namespace ts_support::fleece {
    void updateProperties(FLMutableDict dict, FLSlice keyPath, const nlohmann::json &value);

    void removeProperties(FLMutableDict dict, FLSlice keyPath);
}
